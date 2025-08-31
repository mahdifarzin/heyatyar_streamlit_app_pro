import streamlit as st
import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv
import re
import time # Import time for sleep
from litellm import completion, RateLimitError # Import RateLimitError

# Load environment variables from a .env file (if it exists).
load_dotenv()


# --- Database Functions ---

def create_connection(db_file):
    """Create a database connection to the SQLite database specified by db_file."""
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except sqlite3.Error as e:
        st.error(f"Error connecting to database: {e}")
        return None


def add_employee(conn, employee_data):
    """Insert a new employee record into the EMPLOYEE table."""
    sql = """ INSERT INTO EMPLOYEE(NAME, SALARY, AGE, GENDER, DESIGNATION, WORKING_HOURS, MONTHLY_LUNCH_BILL, BONUS)
              VALUES(?, ?, ?, ?, ?, ?, ?, ?) """
    cur = conn.cursor()
    try:
        cur.execute(sql, employee_data)
        conn.commit()
        return True
    except sqlite3.Error as e:
        st.error(f"Error adding employee: {e}")
        return False


def get_all_employees(conn):
    """Retrieve all data from the EMPLOYEE table."""
    sql = "SELECT * FROM EMPLOYEE"
    cur = conn.cursor()
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        return rows
    except sqlite3.Error as e:
        st.error(f"Error retrieving data: {e}")
        return []

def delete_employee(conn, employee_id=None, employee_name=None):
    """
    Delete an employee record from the EMPLOYEE table by ID or Name.
    Provide either employee_id or employee_name, but not both.
    """
    cur = conn.cursor()
    if employee_id is not None:
        sql = "DELETE FROM EMPLOYEE WHERE ID = ?"
        param = (employee_id,)
    elif employee_name is not None:
        sql = "DELETE FROM EMPLOYEE WHERE NAME = ?"
        param = (employee_name,)
    else:
        st.error("Please provide either an Employee ID or a Name to delete.")
        return False

    try:
        cur.execute(sql, param)
        conn.commit()
        # Check if any row was actually deleted
        if cur.rowcount > 0:
            return True
        else:
            if employee_id is not None:
                st.warning(f"No employee found with ID '{employee_id}'.")
            elif employee_name is not None:
                st.warning(f"No employee found with Name '{employee_name}'.")
            return False
    except sqlite3.Error as e:
        st.error(f"Error deleting employee: {e}")
        return False

def search_employee(conn, employee_id=None, employee_name=None):
    """
    Search for an employee record from the EMPLOYEE table by ID or Name.
    Returns the employee record as a list of tuples, or an empty list if not found.
    """
    cur = conn.cursor()
    if employee_id is not None:
        sql = "SELECT * FROM EMPLOYEE WHERE ID = ?"
        param = (employee_id,)
    elif employee_name is not None:
        sql = "SELECT * FROM EMPLOYEE WHERE NAME = ?"
        param = (employee_name,)
    else:
        st.error("Please provide either an Employee ID or a Name to search.")
        return []

    try:
        cur.execute(sql, param)
        rows = cur.fetchall()
        return rows
    except sqlite3.Error as e:
        st.error(f"Error searching employee: {e}")
        return []

def execute_sql_query(sql, db):
    """Executes a given SQL query against the specified database."""
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    try:
        cur.execute(sql)
        rows = cur.fetchall()
        conn.commit() # Commit changes for DML operations (INSERT, UPDATE, DELETE)
        return rows
    except sqlite3.Error as e:
        return f"Error executing SQL query: {e}"
    finally:
        conn.close()

# Prompt for the LLM
prompt_text = """
    You are an expert in converting English questions to SQL query!
    The SQL database has the name EMPLOYEE and has the following columns -
    ID, NAME, SALARY, AGE, GENDER, DESIGNATION, WORKING_HOURS, MONTHLY_LUNCH_BILL, BONUS
    \n\nFor example,\nExample 1 - Retrieve all employees
    the SQL command will be something like this SELECT * FROM EMPLOYEE;
    \nExample 2 - Retrieve employees with a specific salary range
    the SQL command will be something like this SELECT * FROM EMPLOYEE
    WHERE SALARY BETWEEN 50000 AND 70000;
    \nExample 3 - What is the average salary of employees?
    the SQL command will be something like this SELECT AVG(SALARY) FROM EMPLOYEE;
    \nExample 4 - How many male employees are there?
    the SQL command will be something like this SELECT COUNT(*) FROM EMPLOYEE WHERE GENDER = 'Male';
    \nExample 5 - List employees older than 30 with a bonus greater than 0.
    the SQL command will be something like this SELECT * FROM EMPLOYEE WHERE AGE > 30 AND BONUS > 0;
"""

def get_llm_response(question, system_prompt, max_retries=10, initial_delay=2): # Increased retries and initial delay
    """
    Gets an SQL query from the LLM based on the user's question and a system prompt.
    Uses litellm for API calls with exponential backoff.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question}
    ]
    retries = 0
    delay = initial_delay
    while retries < max_retries:
        try:
            with st.spinner(f"Asking AI... (Attempt {retries + 1}/{max_retries})"): # Add spinner
                response = completion(
                    model="openrouter/moonshotai/kimi-k2:free", # Specify the model for LiteLLM
                    messages=messages,
                    api_key=os.getenv("OPENROUTER_API_KEY") # Use the OpenRouter API key
                )
            return response.choices[0].message.content
        except RateLimitError as e:
            retries += 1
            if retries < max_retries:
                st.warning(f"Rate limit hit. Retrying in {delay} seconds... (Attempt {retries}/{max_retries})")
                time.sleep(delay)
                delay *= 2 # Exponential backoff
            else:
                st.error(f"Max retries reached. Error getting response from LLM: {e}")
                return f"Error: Could not get response from LLM after multiple retries. Details: {e}"
        except Exception as e:
            st.error(f"Error getting response from LLM: {e}")
            return f"Error: Could not get response from LLM. Details: {e}"
    return "Error: Failed to get LLM response." # Should not be reached if max_retries is handled


# --- Streamlit App UI and Logic ---

st.set_page_config(page_title="Employee Data Management", layout="wide")
st.title("Employee Data Management")
st.subheader("Add a New Employee Record")

# Create a connection to the database
database = "company.db"

conn = create_connection(database)

if conn:
    try:
        # Use a Streamlit form for better input management
        with st.form("new_employee_form"):
            st.write("Fill in the details for the new employee. **Required fields are marked with an asterisk (*)**")

            # Form input fields
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Name *", key="name_input")
                salary = st.number_input("Salary", min_value=0.0, step=1000.0, key="salary_input")
                age = st.number_input("Age", min_value=18, step=1, key="age_input")
                gender = st.selectbox("Gender", ["Male", "Female", "Other"], key="gender_input")

            with col2:
                designation = st.text_input("Designation *", key="designation_input")
                working_hours = st.number_input("Working Hours", min_value=0, step=1, key="hours_input")
                lunch_bill = st.number_input("Monthly Lunch Bill", min_value=0.0, step=10.0, key="lunch_bill_input")
                bonus = st.number_input("Bonus", min_value=0.0, step=100.0, key="bonus_input")

            submit_button = st.form_submit_button("Add Employee")

        if submit_button:
            # Basic validation
            if not name or not designation:
                st.warning("Please fill out the required fields: Name and Designation.")
            else:
                employee_data = (name, salary, age, gender, designation, working_hours, lunch_bill, bonus)
                if add_employee(conn, employee_data):
                    st.success(f"Employee '{name}' added successfully!")
                else:
                    st.error("Failed to add employee. Check the console for details.")

        # --- Delete employee functionality ---
        st.subheader("Remove an Employee Record")
        with st.form("delete_employee_form"):
            st.write("Choose how to identify the employee you wish to remove.")
            delete_by_option = st.radio("Delete by:", ("ID", "Name"), key="delete_by_option")

            employee_id_to_delete = None
            employee_name_to_delete = None

            if delete_by_option == "ID":
                employee_id_to_delete = st.number_input("Employee ID", min_value=1, step=1, key="employee_id_to_delete")
            else: # delete_by_option == "Name"
                employee_name_to_delete = st.text_input("Employee Name", key="employee_name_to_delete")

            delete_button = st.form_submit_button("Remove Employee")

        if delete_button:
            if delete_by_option == "ID" and employee_id_to_delete:
                if delete_employee(conn, employee_id=employee_id_to_delete):
                    st.success(f"Employee with ID '{employee_id_to_delete}' removed successfully!")
            elif delete_by_option == "Name" and employee_name_to_delete:
                if delete_employee(conn, employee_name=employee_name_to_delete):
                    st.success(f"Employee with Name '{employee_name_to_delete}' removed successfully!")
            else:
                st.warning("Please provide a value for deletion.")

        # --- Search employee functionality ---
        st.subheader("Search Employee Record")
        with st.form("search_employee_form"):
            st.write("Choose how to search for an employee.")
            search_by_option = st.radio("Search by:", ("ID", "Name"), key="search_by_option_search") # Changed key to avoid conflict

            employee_id_to_search = None
            employee_name_to_search = None

            if search_by_option == "ID":
                employee_id_to_search = st.number_input("Employee ID", min_value=1, step=1, key="employee_id_to_search")
            else: # search_by_option == "Name"
                employee_name_to_search = st.text_input("Employee Name", key="employee_name_to_search")

            search_button = st.form_submit_button("Search Employee")

        if search_button:
            search_results = []
            if search_by_option == "ID" and employee_id_to_search:
                search_results = search_employee(conn, employee_id=employee_id_to_search)
            elif search_by_option == "Name" and employee_name_to_search:
                search_results = search_employee(conn, employee_name=employee_name_to_search)
            else:
                st.warning("Please provide a value for search.")

            if search_results:
                st.subheader("Search Results:")
                columns = ["ID", "NAME", "SALARY", "AGE", "GENDER", "DESIGNATION", "WORKING_HOURS", "MONTHLY_LUNCH_BILL",
                           "BONUS"]
                df_search = pd.DataFrame(search_results, columns=columns)
                st.dataframe(df_search, use_container_width=True)
            else:
                st.info("No employee found matching your search criteria.")

        # --- AI Query Functionality ---
        st.subheader("Ask AI about Employee Data")
        with st.form("ai_query_form"):
            ai_question = st.text_area("Enter your question about employee data:", key="ai_question_input")
            ask_ai_button = st.form_submit_button("Ask AI")

        if ask_ai_button and ai_question:
            st.info("Getting answer from AI...")
            response_from_llm = get_llm_response(ai_question, prompt_text)

            # Attempt to extract SQL from the LLM's response.
            sql_match = re.search(r"```sql\s*(.*?)\s*```", response_from_llm, re.DOTALL | re.IGNORECASE)
            if sql_match:
                sql_query_to_execute = sql_match.group(1).strip()
            else:
                # Fallback if no markdown block is found, assume the whole response is the SQL
                sql_query_to_execute = response_from_llm.strip()

            if "Error: Could not get response from LLM" in sql_query_to_execute:
                st.error(sql_query_to_execute)
            elif not (sql_query_to_execute.lower().startswith("select") or \
                      sql_query_to_execute.lower().startswith("insert") or \
                      sql_query_to_execute.lower().startswith("update") or \
                      sql_query_to_execute.lower().startswith("delete")):
                st.warning("The AI did not return a valid SQL query (must start with SELECT, INSERT, UPDATE, or DELETE). Please refine your question.")
            else:
                data = execute_sql_query(sql_query_to_execute, "company.db")

                if "Error executing SQL query" in str(data):
                    st.error(data)
                else:
                    st.subheader("AI Answer:")
                    if data:
                        # If it's a single value (e.g., COUNT, AVG, or specific salary), display it directly
                        if len(data) == 1 and len(data[0]) == 1:
                            st.success(f"The answer is: **{data[0][0]}**")
                        else:
                            # Otherwise, display as a DataFrame
                            columns = ["ID", "NAME", "SALARY", "AGE", "GENDER", "DESIGNATION", "WORKING_HOURS", "MONTHLY_LUNCH_BILL", "BONUS"]
                            # Attempt to infer columns if it's a SELECT * or a simple query
                            if sql_query_to_execute.lower().startswith("select * from employee"):
                                df_ai_results = pd.DataFrame(data, columns=columns)
                            elif len(data) > 0 and isinstance(data[0], tuple):
                                # Attempt to create generic columns if specific ones aren't known
                                # This is a fallback if the AI returns a subset of columns or aggregation
                                inferred_columns = [f"Column_{i+1}" for i in range(len(data[0]))]
                                df_ai_results = pd.DataFrame(data, columns=inferred_columns)
                            else:
                                # Handle cases where data might be a single value (e.g., COUNT, AVG)
                                df_ai_results = pd.DataFrame(data)

                            st.dataframe(df_ai_results, use_container_width=True)
                    else:
                        st.info("No data found for your AI query.")
        elif ask_ai_button and not ai_question:
            st.warning("Please enter a question for the AI.")


        # --- Display all employees in a table ---
        st.subheader("Current Employee Roster")

        employee_rows = get_all_employees(conn)
        if employee_rows:
            columns = ["ID", "NAME", "SALARY", "AGE", "GENDER", "DESIGNATION", "WORKING_HOURS", "MONTHLY_LUNCH_BILL",
                       "BONUS"]
            df = pd.DataFrame(employee_rows, columns=columns)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("The employee table is currently empty.")
    finally:
        # Always close the connection
        conn.close()
else:
    st.error("Could not connect to the database. Please ensure 'company.db' exists.")

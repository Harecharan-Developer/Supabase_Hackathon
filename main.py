import requests

import streamlit as st
from streamlit_option_menu import option_menu
import google.generativeai as genai
from PIL import Image
from PyPDF2 import PdfReader
import gspread
import os
from dotenv import load_dotenv
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
from supabase import create_client, Client 
from postgrest.exceptions import APIError
import time
from faker import Faker
import random
from datetime import date
import calendar
import json

load_dotenv()

# Get the path to the secret file from the environment variable
secret_file_path = os.getenv('CREDENTIALS_JSON')

# Check if the secret file exists
if secret_file_path:
    # Read the content of the secret file
    with open(secret_file_path, 'r') as f:
        credentials_data = json.load(f)
        CREDENTIALS_JSON = credentials_data.get('CREDENTIALS_JSON')
SHEET_KEY=os.getenv('SHEET_KEY')     
GEMINI_KEY=os.getenv('GEMINI_KEY')
SUPABASE_KEY=os.getenv('SUPERBASE_KEY')
SUPABASE_URL=os.getenv('SUPERBASE_URL')
BUCKET_URL=os.getenv('BUCKET_URL')

supabase : Client = create_client(SUPABASE_URL,SUPABASE_KEY)

gc = gspread.service_account(filename=CREDENTIALS_JSON)
sheet = gc.open_by_key(SHEET_KEY)
worksheet = sheet.sheet1

# Ensure the API key is configured
genai.configure(api_key=GEMINI_KEY)
model1 = genai.GenerativeModel('gemini-pro')
model2 = genai.GenerativeModel('gemini-pro-vision')



# Function to generate a unique user_id based on the current time
def generate_unique_user_id():
    # Use the current time in milliseconds as the user_id
    user_id = int(time.time() * 1000)
    return user_id

class gemini_model:
    def __init__(self):
        self.response_dict = {}  # Make response_dict a class attribute
        self.details = []  # Make details a class attribute
        self.input_prompt = """
            You are an expert in understanding invoices.
            You will receive input images as invoices & text
            you will have to answer questions based on the input image
            """

    # Function to get the response for PDF input
    def get_gemini_response_pdf(self,input_prompt, context):
        response = model1.generate_content([context, input_prompt])
        return response.text

    # Function to get the response for image input
    def get_gemini_response_image(self,input, image, prompt):
        response = model2.generate_content([input, image[0], prompt])
        return response.text

    # Function to extract text from PDF
    def get_pdf_text(self,pdf_docs):
        text = ""
        for pdf in pdf_docs:
            pdf_reader = PdfReader(pdf)
            for page in pdf_reader.pages:
                text += page.extract_text()
        return text

    # Function to set up image data for processing
    def input_image_setup(self,uploaded_file):
        if uploaded_file is not None:
            bytes_data = uploaded_file.getvalue()
            image_parts = [{"mime_type": uploaded_file.type, "data": bytes_data}]
            return image_parts
        else:
            raise FileNotFoundError("No file uploaded")

    def main_model(self):
        input = '''give me the details of the invoice like invoice name, invoice number as a integer, invoice company, date, total amount as a integer, no of items as a integer,
        i need only these fields do not give me any extra details ok?
        if any field is not available, return them as NULL,
        i need all detials as a python dictionary  '''

        uploaded_file = st.file_uploader("Upload an image or PDF...", type=["jpg", "jpeg", "png", "pdf"])

        if uploaded_file is not None:
            if uploaded_file.type.startswith('image/'):
                image = Image.open(uploaded_file)
                st.image(image, caption="Uploaded Image.", use_column_width=True)
                image_data = self.input_image_setup(uploaded_file)  
                response = self.get_gemini_response_image(self.input_prompt, image_data, input)
            elif uploaded_file.type == 'application/pdf':
                st.write("Uploaded PDF:", uploaded_file.name)
                image = None
                context = self.get_pdf_text([uploaded_file])
                response = self.get_gemini_response_pdf(input, context)
            else:
                raise ValueError("Unsupported file type.")

            st.subheader("The Response is")
            response = response.replace("python", "")
            details = self.extract_invoice_details(response)
            updated_details=self.display_invoice_fields(details)
        

            if st.button("Submit"):
                self.upload_to_database(updated_details)
                st.write("Successfully uploaded")
# Button for uploading to Supabase Buckets
                if st.button("Upload to Database"):
                    user_id = st.session_state.user_id  # Assuming you have the user_id stored in session_state
                    invoice_id = updated_details['invoice_id']  # Assuming 'invoice_id' is a key in updated_details
                    file_name = f"{user_id}_{invoice_id}.pdf" if uploaded_file.type == 'application/pdf' else f"{user_id}_{invoice_id}.png"
                    bucket_url = self.upload_to_supabase_bucket(uploaded_file, file_name)
                    st.write(f"File uploaded to Supabase Buckets with URL: {bucket_url}")



    def upload_to_supabase_bucket(file, file_name):
        resp=supabase.storage().from_("invoice_bucket").upload(file,file)
        print(resp)
    def extract_invoice_details(self, response):
        details = []
        respons_lst = response.split("\n")
        for i in respons_lst[:-1]:
            if i not in ['{', '}', "'", "```"]:
                details.append(i)
        details.pop(0)
        details = [str(x) for x in details]
        response_dict = {}
        for x in details:
            key, val = x.split(':', 1)
            key = key.strip().strip('"')
            key = key.replace(":", "")
            val = val.replace(",", "").strip()  # Strip any whitespace
            response_dict[key] = val
        # Ensure 'invoice_date' key exists, otherwise set it to today's date
        if 'invoice_date' not in response_dict:
            response_dict['invoice_date'] = date.today().strftime("%Y-%m-%d")
        print(response_dict)
        return response_dict


    def display_invoice_fields(self, details):
        fake = Faker()

        st.write(details)
        empty_dict={"invoice_name": fake.name(), "invoice_number": random.randint(1000000,9999999), "invoice_company": fake.company(), "date": date.today().strftime("%Y-%m-%d"), "total_amount": 1, "no_of_items": 1}
        for key, value in empty_dict.items():
            if details.get(key) is not None and details[key] != "NULL" and details[key] != "null" and details[key] != "None" and details[key] != "none" and details[key] != "none" and details[key] != "":
                empty_dict[key] = st.text_input(key, value=details[key])
            else:
                empty_dict[key] = st.text_input(key, value=empty_dict[key])
        print("empty_dict=",empty_dict)
        return empty_dict 

    def upload_to_database(self, details):
        print("details=",details)
        values = [value.replace('"', '') for value in details.values()]
        worksheet.append_row(values)
        try:
            supabase.table("Invoices").insert({
                "invoice_date": details['date'],
                "user_id": st.session_state.user_id,
                "invoice_id": details['invoice_number'],
                "invoice_name": details['invoice_name'],
                "invoice_company": details['invoice_company'],
                "invoice_no": details['invoice_number'],
                "total_amount": float(details['total_amount']),
                "no_of_items": int(details['no_of_items']),
                "invoices_user_id": str(st.session_state.user_id) + "_" + str(details['invoice_number'])
            }).execute()
        except APIError as e:
            if '23505' in str(e):
                st.error('This invoice has already been uploaded.')
            if '22003' in str(e):
                st.error('Please ensure that the total amount and no of items are integers.')
            if '22P02' in str(e):
                st.error('Please ensure that the invoice number is an integer if no invoice number, enter 0.')
                
                
class user_interface:
    def __init__(self):
        self.username = ""
        self.password = ""

    def authenticate_and_get_user_id(self, username, password):
        try:
            data = supabase.table("Users").select("user_id").eq("username", username).eq("password", password).execute()

            if data.data:
                # Assuming the first match is the correct one since usernames should be unique
                user_id = data.data[0]['user_id']
                return True, user_id  # Return both authentication success and user_id
            else:
                return False, None
        except Exception as e:
            print(f"An error occurred during authentication: {e}")
            return False, None

    def login_page(self):
        st.title("Login")
        self.username = st.text_input("Username")
        self.password = st.text_input("Password", type="password")
        login_button = st.button("Login")

        if login_button:
            authenticated, user_id = self.authenticate_and_get_user_id(self.username, self.password)
            if authenticated:
                st.session_state['logged_in'] = True
                st.session_state['user_id'] = user_id  # Store the user_id in the session state
                st.session_state.page = 'home'  # Redirect to home page after login
                st.success("Succesful Login")
                st.experimental_rerun()
            else:
                st.error("Invalid username or password.")

        if st.button("Register"):
            st.session_state.page = 'register'
            st.experimental_rerun()

    def registration_page(self):
        st.title("Registration")
        email = st.text_input("Email", key="email_input")
        username = st.text_input("Username", key="username_input")
        password = st.text_input("Password", type="password", key="password_input")
        confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password_input")
        phone_no = st.text_input("Phone Number", key="phone_input")
        address = st.text_input("Address", key="address_input")
        
        register_button = st.button("Register", key="register_button")
        back_to_login_button = st.button("Back to Login")

        if register_button:
            if not email or not username or not password or not confirm_password or not phone_no or not address:
                st.error("Please fill in all registration details.")
            elif password != confirm_password:
                st.error("Passwords do not match.")
            else:
                unique_user_id = generate_unique_user_id()
                response = supabase.table("Users").insert({
                    "user_id": unique_user_id,
                    "username": username,
                    "password": password,
                    "email": email,
                    "phone_no": phone_no,
                    "address": address
                }).execute()
                

                st.success("Registration successful! Click login button to login ")
                st.session_state.page = 'login'
                st.experimental_rerun()

        if back_to_login_button:
            st.session_state.page = 'login'
            st.experimental_rerun()

    def fetch_user_profile(self, user_id):
        try:
            data = supabase.table("Users").select("*").eq("user_id", user_id).execute()

            if data.data:
                user_data = data.data[0]
                formatted_user_data = {
                    'name': user_data['username'],
                    'email': user_data['email'],
                    'phone_number': user_data['phone_no'],
                    'username': user_data['username'],
                    'address': user_data['address'],
                    # 'profile_photo_url': 'https://picsum.photos/200/300?random=1'
                }
                return formatted_user_data
            else:
                return {
                    'name': 'User not found',
                    'email': '',
                    'phone_number': '',
                    'username': '',
                    'address': '',
                    # 'profile_photo_url': 'https://picsum.photos/200/300?random=2'
                }
        except Exception as e:
            print(f"An error occurred: {e}")
            return {
                'name': 'Error fetching profile',
                'email': '',
                'phone_number': '',
                'username': '',
                'address': '',
                # 'profile_photo_url': 'https://picsum.photos/200/300?random=3'
            }

    def display_profile_page(self):
        user_id = st.session_state.user_id 
        user_data = self.fetch_user_profile(user_id)

        # Define custom CSS styles for the user information section
        custom_css = """
        <style>
        .user-info {
            background-color: #f4f4f4;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            margin-bottom: 20px;
        }
        .user-info h3 {
            color: green;
        }
        .user-info p {
            margin-bottom: 10px;
        }
        </style>
        """

        # Render the custom CSS styles
        st.write(custom_css, unsafe_allow_html=True)

        # Render the user information section
        st.write(f'<div class="user-info">'
                f'<h3>Name: {user_data["name"]}</h3>'
                f'<p>Email: {user_data["email"]}</p>'
                f'<p>Phone Number: {user_data["phone_number"]}</p>'
                f'<p>Username: {user_data["username"]}</p>'
                f'<p>Address: {user_data["address"]}</p>'
                f'</div>', unsafe_allow_html=True)


    def home_page(self):
        st.title("Welcome to Invoice Management Tool")
        st.write("Efficiently manage your invoices with our user-friendly and intuitive platform. Say goodbye to the hassle of manual invoicing and embrace the simplicity of our streamlined solution.")
        st.write("If I win(unlikely though) I would like to be compensated with an internship instead.As for the airpods , I would like its value  to be donated to a charity or somewhere :)  ")
        # Custom CSS for the divs
        custom_css = """
        <style>
        .container {
            justify-content: space-between;
            margin-top: -20px;
            
        }
        .card {
            width: 100%;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s;
            margin-bottom: 20px;
        }

            .card:hover {
                transform: translateY(-5px);
                /* Add the following lines to zoom in the card */
                transition: transform 0.3s;
                transform: scale(1.1);
            }
        
        .card h3 {
            color: #fff;
            margin-bottom: 10px;
        }
        .card p {
            color: #eee;
            margin-bottom: 20px;
        }
        .card.postgres {
            background: linear-gradient(to bottom, #2c3e50, #3498db);
        }
        .card.oauth {
            background: linear-gradient(to bottom, #27ae60, #2ecc71);
        }
        .card.gemini {
            background: linear-gradient(to bottom, #8e44ad, #9b59b6);
        }
        .card.buckets {
            background: linear-gradient(to bottom, #e67e22, #f39c12);
        }
        </style>
        """

        # Render the custom CSS styles
        st.write(custom_css, unsafe_allow_html=True)

        # Render the divs with headings and content
        st.write("""
        <div class="container">
            <div class="card postgres">
                <h3>Supabase PostgreSQL</h3>
                <p>Supabase is used for storing user data securely in a PostgreSQL database.
                We use this for storing user details and the details of their invoice after 
                being extracted.
                </p>
            </div>
            <div class="card oauth">
                <h3>OAuth Integration</h3>
                <p>Planning to integrate OAuth for secure authentication. Supabase python support for documentation is very less. Kindl request supabase team to further look into this</p>
            </div>
            <div class="card gemini">
                <h3>Gemini API</h3>
                <p>Uses Gemini API to extract details from invoices and uses supabase to store the extracted details
                planning to use supabase edge functions to run my own model in the near future .</p>
            </div>
            <div class="card buckets">
                <h3>Supabase Buckets</h3>
                <p>I have tried to use Supabase Buckets for enhanced data management.But its not completely working and I need help guys ;(</p>
            </div>
            
        </div>
        """, unsafe_allow_html=True)

    def extract_date_and_amount(self, data):
        date_list = []
        for d in data:
            if d.get('invoice_date') is not None:  # Check if invoice_date is not null
                date_list.append({'invoice_date': pd.to_datetime(d['invoice_date']), 'total_amount': d['total_amount']})
        return pd.DataFrame(date_list)

    def invoice_plot(self):
        # Streamlit app
        st.title('Invoice Analysis')
        user_id = st.session_state.user_id 
        invoices = supabase.table("Invoices").select("*").eq("user_id", user_id).execute().data
        if len(invoices)==0:
            st.write("No Invoice available for Analytics")
        else:
            # Convert list of dictionaries to DataFrame
            df = self.extract_date_and_amount(invoices)

            if df.empty:
                st.warning('No valid data available.')
                return

            # Plot month vs amount for each year
            years = sorted(df['invoice_date'].dt.year.unique())
            for year in years:
                st.subheader(f'Month vs Amount for {year}')
                filtered_data = df[df['invoice_date'].dt.year == year]

                # Plotting
                fig, ax = plt.subplots(figsize=(10, 6))
                # Plot using month names as x-axis labels
                months = range(1, 13)
                month_names = [calendar.month_name[i] for i in months]
                ax.bar(filtered_data['invoice_date'].dt.month, filtered_data['total_amount'])
                ax.set_xticks(months)
                ax.set_xticklabels(month_names, rotation=90)  # Set month names as x-axis labels vertically
                ax.set_xlabel('Month')
                ax.set_ylabel('Amount')
                ax.set_title(f'Month vs Amount for {year}')
                st.pyplot(fig)
                self.download_plot_button(fig, f'Month_vs_Amount_{year}.png')

            # Plot year vs total amount
            st.subheader('Year vs Total Amount')
            year_total_amount = df.groupby(df['invoice_date'].dt.year)['total_amount'].sum()
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.plot(year_total_amount.index, year_total_amount.values, marker='o')
            ax.set_xlabel('Year')
            ax.set_ylabel('Total Amount')
            ax.set_title('Year vs Total Amount')
            st.pyplot(fig)
            self.download_plot_button(fig, 'Year_vs_Total_Amount.png')

    def download_plot_button(self, fig, filename):
        img_data = BytesIO()
        fig.savefig(img_data, format='png')
        img_data.seek(0)
        st.download_button(label='Download Plot', data=img_data, file_name=filename, mime='image/png')
    
    
    
    
    def invoice_main(self):
        st.title("Invoice Pages")

        # Fetch user_id from session state
        user_id = st.session_state.user_id 

        # Fetch all invoices from the 'Invoices' table based on the user_id
        invoices = supabase.table("Invoices").select("*").eq("user_id", user_id).execute().data

        # Filter options
        filter_options = ["No Filter", "No of Items Less Than", "No of Items Greater Than", "Total Amount Less Than", "Total Amount Greater Than"]
        selected_filter = st.selectbox("Filter By", filter_options)

        # If user selects a filter option
        if selected_filter != "No Filter":
            # Get filter input from user
            filter_input = st.number_input(f"Enter Value to Filter {selected_filter}", min_value=0)

            # Filter invoices based on selected option
            if selected_filter == "No of Items Less Than":
                invoices = [invoice for invoice in invoices if int(invoice['no_of_items']) < filter_input]
            elif selected_filter == "No of Items Greater Than":
                invoices = [invoice for invoice in invoices if int(invoice['no_of_items']) > filter_input]
            elif selected_filter == "Total Amount Less Than":
                invoices = [invoice for invoice in invoices if int(invoice['total_amount']) < filter_input]
            elif selected_filter == "Total Amount Greater Than":
                invoices = [invoice for invoice in invoices if int(invoice['total_amount']) > filter_input]

        # Display filtered invoices
        st.write("Filtered Invoices:")
        for invoice in invoices:
            st.write("Invoice ID:", invoice['invoice_id'])
            st.write("Invoice Name:", invoice['invoice_name'])
            st.write("Invoice Company:", invoice['invoice_company'])
            st.write("Invoice Number:", invoice['invoice_no'])
            st.write("Total Amount:", invoice['total_amount'])
            st.write("No of Items:", invoice['no_of_items'])
            st.write("Invoice Date:", invoice['invoice_date'])
            st.write("---------------")


def main():
    st.set_page_config(page_title="Gemini Demo")
    ui = user_interface()
    g_model = gemini_model()

    if 'page' not in st.session_state:
        st.session_state.page = 'login'

    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        if st.session_state.page == 'login':
            ui.login_page()
        elif st.session_state.page == 'register':
            ui.registration_page()
    else:
        with st.sidebar:
            selected = option_menu(
                menu_title=None,
                options=["🏠Home", "👤Profile", "📄Invoices","📊Analytics","📁Upload New Invoice", "🚪Logout"]
            )

            if selected == "🏠Home":
                st.session_state.page = 'home'
            if selected == "👤Profile":
                st.session_state.page = 'profile'
            if selected == "📄Invoices":
                st.session_state.page = 'invoices'
            if selected == "📁Upload New Invoice":
                st.session_state.page = 'upload_invoice'
            if selected=="📊Analytics":
                st.session_state.page = 'analytics'
            if selected == "🚪Logout":
                st.session_state.logged_in = False
                st.session_state.page = 'login'
                st.experimental_rerun()

        if st.session_state.page == 'home':
            ui.home_page()
        elif st.session_state.page == 'profile':
            st.title('User Profile Page')
            ui.display_profile_page()
        elif st.session_state.page == 'invoices':
            ui.invoice_main()
        elif st.session_state.page=='analytics':
            ui.invoice_plot()
            
        elif st.session_state.page == 'upload_invoice':
            st.header("Upload Your Invoice")
            g_model.main_model()

if __name__ == "__main__":
    main()
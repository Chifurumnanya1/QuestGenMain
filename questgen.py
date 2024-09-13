import streamlit as st
import openai
import os

# Fetch the API key from Streamlit secrets (set in Streamlit Cloud)
openai_api_key = st.secrets["openai_api_key"]

# Check if the API key is available
if not openai_api_key:
    st.error("API key is missing. Please set the OpenAI API key in Streamlit Secrets.")
else:
    # Set the API key for OpenAI
    openai.api_key = openai_api_key

# Set the page configuration
st.set_page_config(
    page_title="MCQ Generator",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="auto",
)

# Inject custom CSS to style the text input box with an orange outline
st.markdown(
    """
    <style>
    /* Apply a custom orange outline to the text input box */
    .css-1cpxqw2 {
        border: 2px solid #FFA500; /* Orange outline */
        border-radius: 5px;
        padding: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Function to generate MCQs using OpenAI with streaming
def generate_mcqs_streaming(text, num_questions, model="gpt-3.5-turbo-instruct"):
    prompt = f"Generate {num_questions} multiple-choice questions (MCQs) based on the following text:\n{text}\nEach MCQ should have 5 options, and the correct answer should be the first option."

    # Create a completion using the new API structure
    response = openai.completions.create(
        model=model,
        prompt=prompt,
        stream=True  # Enable streaming
    )

    full_response = ""
    for chunk in response:
        # Extract the content from each streamed chunk
        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
        full_response += content
        yield content  # Yield each piece of the response as it is streamed

    return full_response

# Function to format MCQs in the desired output format
def format_mcqs(mcqs):
    formatted_mcqs = ""
    questions = mcqs.split("\n\n")

    for question in questions:
        lines = question.split("\n")
        question_text = lines[0].strip().lstrip("0123456789. ")  # Remove numbering if present
        formatted_mcqs += f"## {question_text}\n"
        for option in lines[1:]:
            option_text = option.strip()[2:].strip()  # Remove the first 2 characters (like "A. ") but not the first letter of the option
            formatted_mcqs += f"** {option_text}\n"
        formatted_mcqs += "\n"

    return formatted_mcqs

# Function to save MCQs to a text file with a dynamic filename
def save_output_to_file(content, filename):
    if not filename.endswith('.txt'):
        filename += '.txt'  # Ensure the file has a .txt extension
    with open(filename, "w") as file:
        file.write(content)

# Streamlit app layout
st.title("MCQ Generator with OpenAI")
st.write("Enter the text below, and the app will generate MCQs based on that text.")

# Input text area
input_text = st.text_area("Input Text", height=200)

# Input for number of questions
num_questions = st.number_input("How many questions would you like to generate?", min_value=1, max_value=20, value=5)

# Text box for the filename with an orange outline
filename = st.text_input("Enter a filename for the output (without extension)", value="generated_mcqs")

# Button to generate MCQs
if st.button("Generate MCQs"):
    # Validate that the filename is not empty
    if not filename.strip():
        st.error("The filename is required. Please enter a valid filename.")
    elif input_text:
        # Display progress message
        st.info(f"Generating MCQs, please wait... (File will be saved as {filename}.txt)")

        # Placeholder to dynamically update the output as it streams in
        output_placeholder = st.empty()

        # Stream the response from OpenAI and update the output in real-time
        full_response = ""
        for chunk in generate_mcqs_streaming(input_text, num_questions):
            full_response += chunk
            output_placeholder.text(full_response)

        # Format MCQs in the desired output format
        formatted_mcqs = format_mcqs(full_response)

        # Display formatted MCQs
        st.subheader("Generated MCQs")
        st.text(formatted_mcqs)

        # Save the formatted MCQs to a text file
        save_output_to_file(formatted_mcqs, filename)

        # Provide a download link for the text file
        with open(f"{filename}.txt", "r") as file:
            st.download_button(f"Download MCQs (Saved as {filename}.txt)", file, f"{filename}.txt")
    else:
        st.warning("Please input text to generate MCQs.")

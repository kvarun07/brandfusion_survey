import pandas as pd
import os
import random
import streamlit as st
import streamlit_survey as ss
from streamlit_gsheets import GSheetsConnection
import json
from PIL import Image
import uuid
from datetime import datetime
from constants import CONSENT_FORM
import base64
import io
# Constants and Configuration
QUESTIONS_PER_MODEL_PAIR = 10
TOTAL_QUESTIONS = QUESTIONS_PER_MODEL_PAIR * 3  # 30 total questions
MODEL_PAIRS = [('model_a', 'model_b'), ('model_b', 'model_c'), ('model_a', 'model_c')]
IMAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "./data/media/")
METADATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "./data/image_brand_mapping.json")

with open(METADATA_FILE, 'r') as f:
    image_to_company_mapping = json.load(f)
image_to_company_mapping = dict(sorted(image_to_company_mapping.items(), key=lambda x: x[0]))

image_list = list(image_to_company_mapping.keys())
company_list = list(set(image_to_company_mapping.values()))
company_list = [company.upper() for company in company_list]


### GOOGLE SHEETS CONNECTION
# st.title("Read Google Sheet as DataFrame")
# conn = st.connection("gsheets", type=GSheetsConnection)
# df = conn.read(worksheet="Test Sheet")
# st.dataframe(df)
# print(df.shape)


# Helper Functions
def is_valid_image_pair(image1_path, image2_path):
    """Check if both images in a pair can be opened."""
    try:
        # Try to open both images
        Image.open(image1_path)
        Image.open(image2_path)
        return True
    except:
        return False

def get_image_pairs():
    """Generate random image pairs for the survey with error handling."""
    # Load company metadata
    company_data = {}

    for image in image_to_company_mapping:
        image_id = image.split('.')[0]
        company_data[image_id] = str(image_to_company_mapping[image]).upper()
    
    image_ids = list(company_data.keys())

    # Randomly sample image pairs for each model comparison
    pairs = []
    for model1, model2 in MODEL_PAIRS:
        remaining_ids = image_ids.copy()
        pair_count = 0
        
        while pair_count < QUESTIONS_PER_MODEL_PAIR and remaining_ids:
            # Sample an ID
            if not remaining_ids:
                raise Exception(f"Not enough valid image pairs for {model1}-{model2} comparison")
                
            image_id = random.choice(remaining_ids)
            remaining_ids.remove(image_id)  # Remove to avoid resampling
            
            # Create paths
            image1_path = os.path.join(IMAGE_DIR, model1, f"{image_id}.jpg")
            image2_path = os.path.join(IMAGE_DIR, model2, f"{image_id}.jpg")
            real_path = os.path.join(IMAGE_DIR, "real", f"{image_id}.jpg")
            
            # Check if both images are valid
            if is_valid_image_pair(image1_path, image2_path):
                pairs.append({
                    'image_id': image_id,
                    'model1': model1,
                    'model2': model2,
                    'image1_path': image1_path,
                    'image2_path': image2_path,
                    'real_path': real_path,
                    'company': company_data.get(image_id, "Unknown Company")  # Add company information
                })
                pair_count += 1
            # If invalid, the loop will continue with next sample
    
    if len(pairs) < TOTAL_QUESTIONS:
        raise Exception(f"Could only generate {len(pairs)} valid pairs out of {TOTAL_QUESTIONS} required")
    
    # Shuffle all pairs
    random.shuffle(pairs)
    
    # Add random order flag to each pair
    for pair in pairs:
        pair['show_first_on_left'] = random.choice([True, False])
    
    return pairs

def format_response_for_sheets(survey, image_pairs):
    """Format survey responses into a row for Google Sheets."""
    survey_json = json.loads(survey.to_json())
    print(survey_json)
    
    # Basic response data
    response_data = {
        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": str(uuid.uuid4()),  # Generate unique user ID
        
        # Introductory questions
        "brand_recognition": ", ".join(survey_json.get("brand_recognition", {}).get("value", [])),
        "social_platforms": ", ".join(survey_json.get("social_platforms", {}).get("value", [])),
        "social_engagement": survey_json.get("social_engagement", {}).get("value", ""),
        "shopping_frequency": survey_json.get("shopping_frequency", {}).get("value", ""),
        "purchase_influences": ", ".join(survey_json.get("purchase_influences", {}).get("value", [])),
        "product_discovery": ", ".join(survey_json.get("product_discovery", {}).get("value", []))
    }
    
    # Add responses for each image comparison question
    for question_idx in range(TOTAL_QUESTIONS):
        response_key = f"q_{question_idx}"
        pair = image_pairs[question_idx]
        
        if response_key in survey_json and "value" in survey_json[response_key]:
            selected_model = survey_json[response_key]["value"]
            
            response_data.update({
                f"q_{question_idx+1}_img": pair['image_id'],
                f"q_{question_idx+1}_pair": f"{pair['model1']}-{pair['model2']}",
                f"q_{question_idx+1}_sel": selected_model
            })
        else:
            # Handle missing responses
            response_data.update({
                f"q_{question_idx+1}_img": pair['image_id'],
                f"q_{question_idx+1}_pair": f"{pair['model1']}-{pair['model2']}",
                f"q_{question_idx+1}_sel": "no_response"
            })
    
    return response_data

def initialize_sheets():
    """Initialize Google Sheets with headers if empty."""
    conn = st.connection("gsheets", type=GSheetsConnection)
    
    try:
        # Try to read existing data
        df = conn.read(worksheet="Output Sheet")
        if df.empty:
            # Create headers for an empty sheet
            sample_response = format_response_for_sheets(survey, st.session_state["image_pairs"])
            headers_df = pd.DataFrame(columns=sample_response.keys())
            conn.update(worksheet="Output Sheet", data=headers_df)
    except Exception as e:
        st.error(f"Failed to initialize sheet: {str(e)}")

def store_state_on_submit(survey):
    """Store survey responses in Google Sheets."""
    try:
        # Format response data
        response_data = format_response_for_sheets(survey, st.session_state["image_pairs"])
        
        # Create a connection object
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # Read existing data
        output_sheet_df = conn.read(worksheet="Output Sheet")
        
        # Append new response
        new_row_df = pd.DataFrame([response_data])
        output_sheet_df = pd.concat([output_sheet_df, new_row_df], ignore_index=True)
        
        # Update sheet
        conn.update(worksheet="Output Sheet", data=output_sheet_df)
        
        # Clear cache and update state
        st.cache_data.clear()
        st.session_state["submitted"] = True
        st.rerun()
        
    except Exception as e:
        st.error(f"Failed to save response: {str(e)}")
        return False
    
    return True

def get_button(label, disabled=False, **kwargs):
    """Generate a button with consistent styling."""
    if callable(disabled):
        # If disabled is a function, evaluate it
        disabled_value = disabled(kwargs.get('pages', None))
    else:
        disabled_value = disabled
        
    return st.button(
        label=label,
        use_container_width=True,
        disabled=disabled_value,
        **kwargs
    )

def get_submit_button():
    """Generate submit button function."""
    return lambda pages: st.button(
        label="Submit",
        use_container_width=True,
        disabled=st.session_state.get("submitted", False) or 
                not st.session_state.get(f"q_{TOTAL_QUESTIONS-1}", None),  # Disable if last question not answered
        key=f"{pages.current_page_key}_submit"
    )

def get_previous_button():
    """Generate previous button function."""
    return lambda pages: st.button(
        label="Previous",
        use_container_width=True,
        on_click=pages.previous,
        disabled=pages.current == 0 or st.session_state.get("submitted", False),
        key=f"{pages.current_page_key}_prev"
    )

def get_next_button():
    """Generate next button function."""
    return lambda pages: st.button(
        label="Next",
        use_container_width=True,
        on_click=pages.next,
        disabled=(pages.current == pages.n_pages - 1) or 
                (pages.current == 0 and not st.session_state.get("agree_value", False)) or
                (pages.current == 2 and not _check_intro_questions_complete()) or  # Check intro questions
                (pages.current > 2 and not st.session_state.get(f"q_{pages.current-3}", None)),  # Check image selection
        key=f"{pages.current_page_key}_next"
    )

def _check_intro_questions_complete():
    """Check if all introductory questions have required responses."""
    survey_json = json.loads(survey.to_json())
    
    # Define required fields and their minimum requirements
    required_fields = {
        "brand_recognition": lambda x: len(x) >= 5,  # At least five brands selected
        "social_platforms": lambda x: len(x) > 0,  # At least one platform selected
        "social_engagement": lambda x: x is not None,  # Must select one option
        "shopping_frequency": lambda x: x is not None,  # Must select one option
        "purchase_influences": lambda x: len(x) > 0,  # At least one influence selected
        "product_discovery": lambda x: len(x) > 0,  # At least one discovery method selected
    }
    
    # Check each required field
    for field, validator in required_fields.items():
        value = survey_json.get(field, {}).get("value", None)
        if not value or not validator(value):
            st.error(f"Please answer all questions before proceeding")
            return False
    
    return True

def get_image_base64(image_path):
    """Convert an image to base64 for embedding in HTML."""
    try:
        img = Image.open(image_path)
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return img_str
    except Exception as e:
        st.error(f"Error encoding image: {str(e)}")
        return None

# -----------------------------------------------------------------------------
# Main Survey Setup

st.set_page_config(
    page_title='Brand Alignment Survey',
    page_icon='🖼️',
)

survey = ss.StreamlitSurvey("Brand Alignment Survey")

if "image_pairs" not in st.session_state:
    st.session_state["image_pairs"] = get_image_pairs()
    st.session_state["submitted"] = False

# Empty placeholder for survey content
empty_placeholder = st.empty()

# Initialize the sheet when the app starts
if "sheets_initialized" not in st.session_state:
    initialize_sheets()
    st.session_state["sheets_initialized"] = True

# Survey pages setup
pages = survey.pages(
    TOTAL_QUESTIONS + 3,  # 60 questions + intro + instructions + demographic questions
    progress_bar=True,
    on_submit=lambda: store_state_on_submit(survey)
)

# Update the button assignments
pages.submit_button = get_submit_button()
pages.prev_button = get_previous_button()
pages.next_button = get_next_button()

# -----------------------------------------------------------------------------
# Survey Content

with pages:
    if pages.current == 0:
        st.write(f"""
        # 🖼️ Brand Alignment Survey
        {CONSENT_FORM}
        """)
        
        agree = ss.CheckBox(
            survey=survey,
            label="I am 18+ years old and agree to participate in this survey.",
            id="agree_box",
            value=False
        ).display()
        
        st.session_state["agree_value"] = agree
        if not agree:
            st.error("Please agree to participate before continuing")
            
    elif pages.current == 1:
        st.write("""
        ## Instructions:

        The questionnaire is divided into two parts:

        **Part - A**  
        You will be asked a few questions about your advertisement consumption and social media exposure.

        **Part - B**  
        You will be shown a series of image pairs. In each question, you will be shown two images generated from the same text description.
        Please select the image that you think is more similar to the reference image in terms of brand characteristics.
        """)
        
    elif pages.current == 2:
        st.write("### Part - A\n#### Introductory Questions")
        
        # Brand recognition
        brands = company_list
        ss.MultiSelect(
            survey,
            "I remember seeing ads for the following brands recently (add at least 5 brands):",
            options=brands,
            id="brand_recognition"
        ).display()
        
        # Social media platforms
        social_platforms = ["Instagram", "Facebook", "Twitter/X", "TikTok", "LinkedIn", "Reddit"]
        ss.MultiSelect(
            survey,
            "Which social media platform do you use the most? (select all that apply)",
            options=social_platforms,
            id="social_platforms"
        ).display()
        
        # Social media engagement
        engagement_options = [
            "Multiple times a day",
            "Once a day",
            "A few times a week",
            "Rarely",
            "Never"
        ]
        ss.Radio(
            survey,
            "How often do you engage with content (likes, shares, comments) on social media?",
            options=engagement_options,
            id="social_engagement"
        ).display()
        
        # Online shopping frequency
        shopping_options = [
            "Multiple times a week",
            "Once a week",
            "A few times a month",
            "Rarely",
            "Never"
        ]
        ss.Radio(
            survey,
            "How frequently do you shop online?",
            options=shopping_options,
            id="shopping_frequency"
        ).display()
        
        # Purchase influences
        influence_options = [
            "Advertisements",
            "Reviews & ratings on e-commerce platforms",
            "Friends & family recommendations",
            "Discounts & promotions",
            "Brand reputation"
        ]
        ss.MultiSelect(
            survey,
            "What influences your online purchase decisions the most? (select all that apply)",
            options=influence_options,
            id="purchase_influences"
        ).display()
        
        # Product discovery
        discovery_options = [
            "Social media ads (Instagram, Facebook, etc.)",
            "Television and OTT Platform Ads (like Youtube, Netflix, Hotstar, etc.)",
            "Friends & family recommendations",
            "E-commerce stores (Amazon, Flipkart, etc.)",
            "Billboards & outdoor ads",
            "Physical store visits",
            "Website Ads",
            "Email Ads",
            "Active product search"
        ]
        ss.MultiSelect(
            survey,
            "How do you discover or learn about new products and brands? (select all that apply)",
            options=discovery_options,
            id="product_discovery"
        ).display()
    
    else:
        # Image comparison questions
        question_idx = pages.current - 3
        pair = st.session_state["image_pairs"][question_idx]
        
        st.write("### Part - B\n#### Select the image more similar to the reference image:")
        # st.write(f"**Company**: {pair['company']}")  # Display company name

        # Get base64 encoding of reference image
        ref_img_base64 = get_image_base64(pair['real_path'])
        
        if ref_img_base64:
            # Create styled container with image embedded directly in HTML
            st.markdown(f"""
            <div style="text-align: center; margin-bottom: 10px;">
                <p style="font-size: 18px;">Company: <strong>{pair['company']}</strong></p>
            </div>

            <div style="text-align: center; margin-bottom: 10px;">
                <p style="font-size: 18px;">Reference Image</p>
            </div>
            
            <div style="
                border: 4px solid #1E90FF;
                border-radius: 10px;
                padding: 10px;
                box-shadow: 0 0 10px rgba(30, 144, 255, 0.5);
                margin-bottom: 20px;
                text-align: center;
                background-color: #f8f9fa;
                max-width: 500px;
                margin-left: auto;
                margin-right: auto;
            ">
                <img src="data:image/jpeg;base64,{ref_img_base64}" 
                     style="max-width: 100%; border-radius: 5px;" 
                     alt="Brand Reference Image">
                <p style="margin-top: 10px; font-size: 14px; color: #555;">Brand Reference Image</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            # Fallback if encoding fails
            st.write(f"**Company**: {pair['company']}")
            st.write("**Reference Image**")
            st.image(
                pair['real_path'],
                width=400,
                caption="Brand Reference Image"
            )

        col1, col2 = st.columns(2)
        
        response_key = f"q_{question_idx}"
        
        # Initialize the response in session state if it doesn't exist
        if response_key not in st.session_state:
            st.session_state[response_key] = None
        
        # Style for clickable images and buttons
        st.markdown("""
        <style>
        .stImage {
            transition: transform 0.2s;
            border-radius: 10px;
        }
        .stImage:hover {
            transform: scale(1.02);
        }
        .selected-image {
            border: 4px solid #00c853;
            box-shadow: 0 0 10px rgba(0,200,83,0.5);
        }
        .stButton button {
            width: 100%;
            margin-top: 10px;
            background-color: #f0f2f6;
            border: 1px solid #e0e0e0;
            color: #262730;
        }
        .stButton button:hover {
            background-color: #e8e8e8;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Left image
        with col1:
            if pair['show_first_on_left']:
                image_path = pair['image1_path']
                model = pair['model1']
            else:
                image_path = pair['image2_path']
                model = pair['model2']
                
            st.image(
                image_path,
                use_container_width=True,
                caption="Image A"
            )
            
            if st.button("Select", key=f"img1_{question_idx}", help="Click to select this image"):
                st.session_state[response_key] = model
                st.session_state[f"radio_{response_key}"] = model
                ss.Radio(survey, label=response_key, options=[pair['model1'], pair['model2']], horizontal=True, visible=False).value = model
                st.rerun()
            
            # Show selection indicator only if this image is selected
            if st.session_state[response_key] == model:
                st.markdown("✅ Selected")
                # st.markdown("✅ Selected:\n" + model + " (" + image_path + ")\n" + "show_first_on_left: " + str(pair['show_first_on_left']))
        
        # Right image
        with col2:
            if pair['show_first_on_left']:
                image_path = pair['image2_path']
                model = pair['model2']
            else:
                image_path = pair['image1_path']
                model = pair['model1']
                
            st.image(
                image_path,
                use_container_width=True,
                caption="Image B"
            )
            
            if st.button("Select", key=f"img2_{question_idx}", help="Click to select this image"):
                st.session_state[response_key] = model
                st.session_state[f"radio_{response_key}"] = model
                ss.Radio(survey, label=response_key, options=[pair['model1'], pair['model2']], horizontal=True, visible=False).value = model
                st.rerun()
            
            # Show selection indicator only if this image is selected
            if st.session_state[response_key] == model:
                st.markdown("✅ Selected")
                # st.markdown("✅ Selected:\n" + model + " (" + image_path + ")\n" + "show_first_on_left: " + str(pair['show_first_on_left']))
        
        # Show current selection status
        if st.session_state[response_key]:
            # Determine the correct label based on the selected model and current layout
            if pair['show_first_on_left']:
                selected_label = "A" if st.session_state[response_key] == pair['model1'] else "B"
            else:
                selected_label = "B" if st.session_state[response_key] == pair['model1'] else "A"
            st.success(f"You selected Image {selected_label}")
        else:
            st.info("Please select one of the images to continue")

if st.session_state["submitted"]:
    empty_placeholder.empty()
    st.success("Thank you for completing the survey!") 
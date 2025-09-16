import streamlit as st
import math
import psycopg2
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import os
import io
import base64


def calculate_bmi(weight, height):
    """Calculate BMI given weight in kg and height in meters"""
    if height <= 0 or weight <= 0:
        return None
    return weight / (height**2)


def classify_bmi(bmi):
    """Classify BMI into categories"""
    if bmi < 18.5:
        return "Underweight", "🔵"
    elif 18.5 <= bmi < 25:
        return "Normal weight", "🟢"
    elif 25 <= bmi < 30:
        return "Overweight", "🟡"
    else:
        return "Obese", "🔴"


def get_health_recommendations(category, age=None, gender=None):
    """Get health recommendations based on BMI category, age, and gender"""
    base_recommendations = {
        "Underweight": [
            "Consult with a healthcare provider to determine underlying causes",
            "Focus on nutrient-dense foods to gain weight healthily",
            "Consider strength training to build muscle mass",
            "Ensure adequate caloric intake for your activity level"
        ],
        "Normal weight": [
            "Maintain your current healthy lifestyle",
            "Continue regular physical activity (150 minutes moderate exercise per week)",
            "Eat a balanced diet rich in fruits, vegetables, and whole grains",
            "Monitor your weight regularly to maintain this healthy range"
        ],
        "Overweight": [
            "Aim for gradual weight loss (1-2 pounds per week)",
            "Increase physical activity to at least 300 minutes per week",
            "Focus on portion control and reducing caloric intake",
            "Consider consulting a nutritionist for personalized advice"
        ],
        "Obese": [
            "Consult with a healthcare provider for a comprehensive weight management plan",
            "Set realistic weight loss goals (5-10% of body weight initially)",
            "Combine dietary changes with regular physical activity",
            "Consider professional support from dietitians or weight loss programs"
        ]
    }

    recommendations = base_recommendations.get(category, []).copy()

    # Age-specific adjustments
    if age:
        if age >= 65:
            if category == "Underweight":
                recommendations.append(
                    "Older adults may need slightly higher BMI for better health outcomes - discuss with your doctor"
                )
            elif category == "Normal weight":
                recommendations.append(
                    "Focus on maintaining muscle mass through resistance training and adequate protein intake"
                )
            elif category in ["Overweight", "Obese"]:
                recommendations.append(
                    "Weight loss for older adults should be supervised by healthcare professionals to preserve muscle mass"
                )
        elif age < 18:
            recommendations.append(
                "BMI interpretation for individuals under 18 may differ - consult with a pediatrician for appropriate guidance"
            )

    # Gender-specific adjustments
    if gender == "Female":
        if category == "Normal weight":
            recommendations.append(
                "Women may need additional iron and calcium in their diet - especially during reproductive years"
            )
        elif category == "Underweight":
            recommendations.append(
                "Underweight in women can affect menstrual health and bone density - consider consulting a healthcare provider"
            )
    elif gender == "Male":
        if category == "Overweight" or category == "Obese":
            recommendations.append(
                "Men tend to carry more visceral fat, which increases health risks - focus on waist circumference reduction"
            )

    return recommendations


def get_bmi_interpretation_note(bmi, age=None, gender=None):
    """Get additional interpretation note based on age and gender"""
    notes = []

    if age and age >= 65:
        notes.append(
            "Note: For adults 65+, slightly higher BMI (23-30) may be associated with better health outcomes."
        )

    if age and age < 18:
        notes.append(
            "Important: This calculator is designed for adults. BMI interpretation for children and teens requires age and sex-specific percentiles."
        )

    if gender == "Female" and 18 <= (age or 30) <= 50:
        notes.append(
            "Note: BMI doesn't account for pregnancy, menstrual cycle variations, or body composition differences."
        )

    return notes


def convert_height_to_meters(feet, inches, unit_system):
    """Convert height to meters based on unit system"""
    if unit_system == "Imperial":
        total_inches = feet * 12 + inches
        return total_inches * 0.0254  # Convert inches to meters
    else:
        return feet / 100  # Convert cm to meters


def convert_weight_to_kg(weight, unit_system):
    """Convert weight to kg based on unit system"""
    if unit_system == "Imperial":
        return weight * 0.453592  # Convert lbs to kg
    else:
        return weight  # Already in kg


def get_connection():
    """Get database connection"""
    return psycopg2.connect(host=os.environ["PGHOST"],
                            database=os.environ["PGDATABASE"],
                            user=os.environ["PGUSER"],
                            password=os.environ["PGPASSWORD"],
                            port=os.environ["PGPORT"])


@st.cache_resource
def init_database():
    """Initialize database schema"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bmi_history (
                id SERIAL PRIMARY KEY,
                height_m DECIMAL(5,3) NOT NULL,
                weight_kg DECIMAL(5,2) NOT NULL,
                bmi DECIMAL(4,1) NOT NULL,
                category VARCHAR(20) NOT NULL,
                unit_system VARCHAR(10) NOT NULL,
                age INTEGER,
                gender VARCHAR(10),
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Database initialization error: {e}")
        return False
    finally:
        cur.close()
        conn.close()


def save_bmi_calculation(height_m,
                         weight_kg,
                         bmi,
                         category,
                         unit_system,
                         age=None,
                         gender=None):
    """Save BMI calculation to database"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO bmi_history (height_m, weight_kg, bmi, category, unit_system, age, gender) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (height_m, weight_kg, bmi, category, unit_system, age, gender))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error saving BMI calculation: {e}")
        return False
    finally:
        cur.close()
        conn.close()


def get_bmi_history():
    """Get BMI history from database"""
    conn = get_connection()
    try:
        df = pd.read_sql_query(
            "SELECT * FROM bmi_history ORDER BY calculated_at DESC LIMIT 50",
            conn)
        return df
    except Exception as e:
        st.error(f"Error loading BMI history: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def calculate_ideal_weight_range(height_m):
    """Calculate ideal weight range based on healthy BMI (18.5-24.9)"""
    min_weight = 18.5 * (height_m**2)
    max_weight = 24.9 * (height_m**2)
    return min_weight, max_weight


def create_bmi_chart(current_bmi, bmi_history_df):
    """Create interactive BMI chart with plotly"""
    fig = go.Figure()

    # BMI categories background using shapes
    fig.add_shape(type="rect",
                  x0=0,
                  x1=1,
                  y0=0,
                  y1=18.5,
                  fillcolor="lightblue",
                  opacity=0.2,
                  line_width=0,
                  xref="paper")
    fig.add_shape(type="rect",
                  x0=0,
                  x1=1,
                  y0=18.5,
                  y1=25,
                  fillcolor="lightgreen",
                  opacity=0.2,
                  line_width=0,
                  xref="paper")
    fig.add_shape(type="rect",
                  x0=0,
                  x1=1,
                  y0=25,
                  y1=30,
                  fillcolor="lightyellow",
                  opacity=0.2,
                  line_width=0,
                  xref="paper")
    fig.add_shape(type="rect",
                  x0=0,
                  x1=1,
                  y0=30,
                  y1=45,
                  fillcolor="lightcoral",
                  opacity=0.2,
                  line_width=0,
                  xref="paper")

    # Add history line if available
    if not bmi_history_df.empty:
        fig.add_trace(
            go.Scatter(x=bmi_history_df['calculated_at'],
                       y=bmi_history_df['bmi'],
                       mode='lines+markers',
                       name='BMI History',
                       line=dict(color='blue', width=2),
                       marker=dict(size=6)))

    # Add current BMI point
    fig.add_trace(
        go.Scatter(x=[datetime.now()],
                   y=[current_bmi],
                   mode='markers',
                   name='Current BMI',
                   marker=dict(size=12, color='red', symbol='star')))

    fig.update_layout(title="BMI Tracking Chart",
                      xaxis_title="Date",
                      yaxis_title="BMI Value",
                      yaxis=dict(range=[15, 45]),
                      height=400)

    return fig


def export_bmi_data(df):
    """Export BMI data as CSV"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="bmi_history.csv">Download BMI History CSV</a>'
    return href


# Initialize database
init_database()

# Streamlit App
st.title("🏥 BMI Calculator")
st.write(
    "Calculate your Body Mass Index and get personalized health recommendations"
)

# Create tabs for different sections
main_tab, history_tab, export_tab = st.tabs(
    ["🧮 Calculator", "📈 History & Charts", "📊 Export Data"])

with main_tab:
    # Unit system selection
    unit_system = st.radio("Choose your preferred unit system:",
                           ["Metric", "Imperial"],
                           horizontal=True)

    # Age and Gender inputs
    col_demo1, col_demo2 = st.columns(2)
    with col_demo1:
        age = st.number_input(
            "Age (optional)",
            min_value=0,
            max_value=120,
            value=0,
            help=
            "Age helps provide more accurate health assessments. Leave as 0 to skip."
        )
    with col_demo2:
        gender = st.selectbox(
            "Gender (optional)", ["", "Male", "Female", "Other"],
            help="Gender considerations for BMI interpretation")

    # Create two columns for input
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📏 Height")
        if unit_system == "Metric":
            height_cm = st.number_input(
                "Height (cm)",
                min_value=50.0,
                max_value=250.0,
                value=170.0,
                step=0.1,
                help="Enter your height in centimeters")
            height_m = height_cm / 100
        else:
            feet = st.number_input("Feet",
                                   min_value=1,
                                   max_value=8,
                                   value=5,
                                   step=1)
            inches = st.number_input("Inches",
                                     min_value=0,
                                     max_value=11,
                                     value=8,
                                     step=1)
            height_m = convert_height_to_meters(feet, inches, "Imperial")

    with col2:
        st.subheader("⚖️ Weight")
        if unit_system == "Metric":
            weight = st.number_input("Weight (kg)",
                                     min_value=20.0,
                                     max_value=300.0,
                                     value=70.0,
                                     step=0.1,
                                     help="Enter your weight in kilograms")
            weight_kg = weight
        else:
            weight = st.number_input("Weight (lbs)",
                                     min_value=44.0,
                                     max_value=660.0,
                                     value=154.0,
                                     step=0.1,
                                     help="Enter your weight in pounds")
            weight_kg = convert_weight_to_kg(weight, "Imperial")

    # Calculate BMI in real-time
    if height_m > 0 and weight_kg > 0:
        bmi = calculate_bmi(weight_kg, height_m)

        if bmi:
            category, emoji = classify_bmi(bmi)

            # Save BMI button
            if st.button("💾 Save BMI Calculation", type="primary"):
                age_val = age if age > 0 else None
                gender_val = gender if gender else None
                if save_bmi_calculation(height_m, weight_kg, bmi, category,
                                        unit_system, age_val, gender_val):
                    st.success("BMI calculation saved successfully!")
                    st.rerun()

        # Display results
        st.markdown("---")
        st.subheader("📊 Your BMI Results")

        # BMI value with large text
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown(f"""
            <div style="text-align: center;">
                <h1 style="font-size: 3em; margin: 0;">{bmi:.1f}</h1>
                <h2 style="margin: 0;">{emoji} {category}</h2>
            </div>
            """,
                        unsafe_allow_html=True)

        # BMI scale visualization
        st.subheader("📈 BMI Scale")

        # Create a visual representation of BMI scale
        scale_data = {
            "Underweight": {
                "range": "< 18.5",
                "color": "#3498db"
            },
            "Normal weight": {
                "range": "18.5 - 24.9",
                "color": "#2ecc71"
            },
            "Overweight": {
                "range": "25.0 - 29.9",
                "color": "#f39c12"
            },
            "Obese": {
                "range": "≥ 30.0",
                "color": "#e74c3c"
            }
        }

        for cat, info in scale_data.items():
            if cat == category:
                st.markdown(f"**→ {cat}**: {info['range']} ← *You are here*")
            else:
                st.markdown(f"{cat}: {info['range']}")

        # Health recommendations
        st.subheader("💡 Health Recommendations")
        age_val = age if age > 0 else None
        gender_val = gender if gender else None
        recommendations = get_health_recommendations(category, age_val,
                                                     gender_val)

        for i, recommendation in enumerate(recommendations, 1):
            st.write(f"**{i}.** {recommendation}")

        # Additional interpretation notes based on age and gender
        interpretation_notes = get_bmi_interpretation_note(
            bmi, age_val, gender_val)
        if interpretation_notes:
            st.subheader("ℹ️ Additional Considerations")
            for note in interpretation_notes:
                st.info(note)

        # Additional information
        st.markdown("---")
        st.info("""
        **Important Note:** BMI is a screening tool and not a diagnostic measure. 
        It doesn't account for muscle mass, bone density, or fat distribution. 
        Always consult with healthcare professionals for personalized health advice.
        """)

        # Display conversion info if using imperial
        if unit_system == "Imperial":
            st.caption(
                f"Converted values: Height = {height_m:.2f}m, Weight = {weight_kg:.1f}kg"
            )

        # Ideal weight range calculation
        st.markdown("---")
        st.subheader("🎯 Ideal Weight Range")
        min_weight, max_weight = calculate_ideal_weight_range(height_m)

        if unit_system == "Metric":
            st.write(
                f"Based on your height, your ideal weight range is **{min_weight:.1f} - {max_weight:.1f} kg**"
            )
        else:
            min_weight_lbs = min_weight / 0.453592
            max_weight_lbs = max_weight / 0.453592
            st.write(
                f"Based on your height, your ideal weight range is **{min_weight_lbs:.1f} - {max_weight_lbs:.1f} lbs**"
            )

    else:
        st.info(
            "Please enter valid height and weight values to calculate your BMI."
        )

# History and Charts Tab
with history_tab:
    st.subheader("📈 BMI History & Visual Charts")

    # Load BMI history
    bmi_history_df = get_bmi_history()

    if not bmi_history_df.empty:
        st.write(f"**Total BMI calculations saved:** {len(bmi_history_df)}")

        # Display interactive chart
        if height_m > 0 and weight_kg > 0 and 'bmi' in locals():
            fig = create_bmi_chart(bmi, bmi_history_df)
            st.plotly_chart(fig, use_container_width=True)

        # Display history table
        st.subheader("📋 Recent BMI History")
        # Format the dataframe for display
        display_df = bmi_history_df.copy()
        display_df['calculated_at'] = pd.to_datetime(
            display_df['calculated_at']).dt.strftime('%Y-%m-%d %H:%M')
        display_df = display_df[[
            'calculated_at', 'bmi', 'category', 'unit_system', 'age', 'gender'
        ]]
        display_df.columns = [
            'Date & Time', 'BMI', 'Category', 'Units', 'Age', 'Gender'
        ]
        st.dataframe(display_df, use_container_width=True)

    else:
        st.info(
            "No BMI history found. Calculate and save some BMI values to see your history and charts here!"
        )

# Export Data Tab
with export_tab:
    st.subheader("📊 Export Your BMI Data")

    bmi_history_df = get_bmi_history()

    if not bmi_history_df.empty:
        st.write(f"**Available data:** {len(bmi_history_df)} BMI calculations")

        # Export options
        st.write("**Export Options:**")

        # CSV Export
        csv_data = bmi_history_df.to_csv(index=False)
        st.download_button(
            label="📥 Download as CSV",
            data=csv_data,
            file_name=f"bmi_history_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
            help=
            "Download your BMI history as a CSV file for Excel or other spreadsheet applications"
        )

        # JSON Export
        json_data = bmi_history_df.to_json(orient='records', date_format='iso')
        st.download_button(
            label="📥 Download as JSON",
            data=json_data,
            file_name=f"bmi_history_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            help=
            "Download your BMI history as a JSON file for data analysis or backup"
        )

        # Data preview
        st.subheader("📋 Data Preview")
        st.dataframe(bmi_history_df.head(10), use_container_width=True)

        if len(bmi_history_df) > 10:
            st.caption(
                f"Showing first 10 rows. Full dataset contains {len(bmi_history_df)} records."
            )

    else:
        st.info(
            "No BMI data available for export. Calculate and save some BMI values first!"
        )

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666;">
    <small>BMI Calculator | Always consult healthcare professionals for medical advice</small>
</div>
""",
            unsafe_allow_html=True)

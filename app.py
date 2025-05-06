from dotenv import load_dotenv
from main import streamlitMain
import streamlit as st
import os
import openai

# טעינת משתני סביבה מקובץ .env
load_dotenv()

# שליפת מפתחות מהסביבה
openai_api_key = os.getenv("OPENAI_API_KEY")
amadeus_key = os.getenv("AMADEUS_API_KEY")
amadeus_secret = os.getenv("AMADEUS_API_SECRET")

# בדיקת מפתחות
if not openai_api_key:
    st.error("❌ לא נטען מפתח ל־OpenAI. ודא שקובץ .env קיים ושכולל את OPENAI_API_KEY.")
if not amadeus_key or not amadeus_secret:
    st.warning("⚠️ מפתחות Amadeus לא נטענו. אפשר להתעלם אם אינם דרושים כרגע.")

# יצירת לקוח OpenAI לפי הממשק החדש
client = openai.OpenAI(api_key=openai_api_key)

# תיבת קלט מהמשתמש
st.title("✈️ GPT + Amadeus חיפוש טיסות")
st.write("הקלד שאילתת טיסה (למשל: טיסה מתל אביב ללונדון שבוע הבא):")

query = st.text_input("")
result = streamlitMain(query)

if query:
    with st.spinner("חושב על זה..."):
        try:
            # response = client.chat.completions.create(
            #     model="gpt-3.5-turbo",
            #     messages=[
            #         {"role": "system", "content": "המערכת מתרגמת שאילתות טיסה לפורמט JSON עבור חיפוש."},
            #         {"role": "user", "content": query}
            #     ]
            # )
            # reply = response.choices[0].message.content
            st.subheader("📦 תוצאה מ־OpenAI:")
            # st.code(reply, language="json")
            st.write(result)
        except Exception as e:
            st.error(f"שגיאה: {e}")

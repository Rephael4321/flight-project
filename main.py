from dotenv import load_dotenv
from openai import OpenAI
import os
import json
import requests
import webbrowser

system_prompt = """
אתה עוזר מומחה לחיפוש טיסות. תפקידך הוא לנתח כל שאילתה של המשתמש – בכל ניסוח אפשרי –
ולהחזיר תשובה בפורמט JSON בלבד, עם כל אחד מהשדות הבאים. עליך לכלול תמיד את כל השדות, גם אם ערכם הוא null:

origin, destination, date, returnDate, adults, children, infants, travelClass, nonStop,
currencyCode, maxPrice, airline, max, budget, seatType, bagsIncluded,
stopovers, days, flexibleDates, preference, note

הנחיות כלליות:
- אל תשתמש בשמות שדות אחרים מאלה.
- החזר תמיד את כל השדות שהוגדרו לעיל, גם אם הם לא הופיעו בשאלה. אם אין ערך ברור – החזר null.
- אם השאלה כללית מדי ולא ניתן להסיק ממנה ערכים ברורים – החזר JSON ריק: {}.
- ענה תמיד בפורמט JSON בלבד – ללא טקסט חופשי, הסברים, כותרות או הקדמות.

מסלולים מרובי יעדים או קונקשנים:
- אם המשתמש מבקש קונקשן מפורש (למשל "עם עצירה בפריז") או מסלול עם יותר מיעד אחד ברצף (למשל "מתל אביב לפריז ואז ללונדון") – החזר את כל המסלול תחת השדה itineraries – מערך של טיסות.
- כל טיסה בתוך itineraries חייבת לכלול את כל השדות הקבועים.
- אל תשתמש בשדה stopovers או note לתיאור תחנות ביניים כשיש רצף טיסות מפורשות – השתמש ב-itineraries.
- אם המשתמש ביקש טיסה עם קונקשן (כמו "עם עצירה אחת"), אך לא ציין יעד עצירה מפורש – החזר טיסה בודדת עם השדה stopovers בהתאם למספר העצירות המבוקש.
- אם מדובר בטיסה אחת בלבד – החזר את כל השדות ברמת JSON רגילה (לא בתוך itineraries).

תאריכים:
- אם המשתמש כותב תאריך בפורמט לא תקני (כמו 20.5.2025, 20/5/25, 20.05.25) – המר אותו לפורמט ISO תקני: YYYY-MM-DD.
- תתייחס לכל פורמט תאריך סביר (נקודות, לוכסנים, מקפים) לפי סדר יום-חודש-שנה.
- אם ניתן להסיק תאריך מתוך הקשר (כגון "שבוע הבא", "אחרי פסח") – המר אותו לתאריך מדויק בהתאם לתאריך ההרצה והשנה הנוכחית.
- אם התאריך חלקי או כללי מדי (למשל "אוגוסט", "חמישי", "קיץ") – החזר date: null.

פרשנות והשלמה:
- התמקד בלחלץ את הכוונה האמיתית של המשתמש – גם אם השפה עממית או לא מדויקת.
- אם צוין יעד כללי (למשל מדינה) – המר לעיר המרכזית (למשל: יוון → ATH).
- אם origin לא צוין – הנח שהכוונה מישראל (TLV).
"""

load_dotenv()

AMADEUS_API_BASE_URL = "https://api.amadeus.com"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AMADEUS_API_KEY = os.getenv("AMADEUS_API_KEY")
AMADEUS_API_SECRET = os.getenv("AMADEUS_API_SECRET")

client = OpenAI(api_key=OPENAI_API_KEY)

# פונקציה לקבלת Access Token מאמדאוס
def get_amadeus_access_token():
    url = f"{AMADEUS_API_BASE_URL}/v1/security/oauth2/token"
    payload = {
        'grant_type': 'client_credentials',
        'client_id': AMADEUS_API_KEY,
        'client_secret': AMADEUS_API_SECRET
    }
    response = requests.post(url, data=payload)

    # הדפסת התגובה כדי לבדוק אם ה-token לא מתפקד כראוי
    print("Response from Amadeus token request:")
    print(response.json())  # הדפסת התשובה
    if response.status_code == 200:
        access_token = response.json().get("access_token")
        return access_token
    else:
        raise Exception(f"Failed to get Amadeus access token: {response.status_code}, {response.text}")


# פונקציה לפירוש שאילתת המשתמש באמצעות GPT (המודל המותאם אישית)
def interpret_user_query(user_query):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # השתמש בשם המודל המותאם אישית שלך
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_query}
        ],
        max_tokens=600,
        temperature=0
    )

    try:
        response_dict = response.model_dump()
        message_content = response_dict["choices"][0]["message"]["content"]
        return json.loads(message_content)
    except (json.JSONDecodeError, KeyError) as e:
        raise Exception("Failed to interpret user query. Ensure GPT returns JSON.") from e

#פונקציה שבודקת ערכים חסרים לטובת המרה לאמדאוס
def fill_missing_fields(parsed_query):
    if "itineraries" in parsed_query:
        for i, flight in enumerate(parsed_query["itineraries"]):
            if not flight.get("date"):
                date = input(f"הזן תאריך יציאה עבור קטע טיסה {i+1} (לדוגמה: 2025-08-10): ")
                flight["date"] = date

            if not flight.get("adults"):
                flight["adults"] = int(input(f"כמה מבוגרים טסים בקטע טיסה {i+1}? (ברירת מחדל: 1): ") or 1)

    else:
        if not parsed_query.get("date"):
            date = input("הזן את תאריך היציאה (לדוגמה: 2025-08-10): ")
            parsed_query["date"] = date

        if not parsed_query.get("destination"):
            dest = input("הזן את יעד הטיסה (לדוגמה: LHR): ")
            parsed_query["destination"] = dest

        if not parsed_query.get("adults"):
            parsed_query["adults"] = int(input("כמה מבוגרים טסים? (ברירת מחדל: 1): ") or 1)

    return parsed_query


#פונקציה להמרת שאילתה מJASON לAMADEUS
def build_amadeus_query(parsed_query: dict) -> dict:
    query = {
        "originLocationCode": parsed_query.get("origin", "TLV"),
        "destinationLocationCode": parsed_query.get("destination"),
        "departureDate": parsed_query.get("date"),
        "adults": parsed_query.get("adults") or 1,
    }

    if parsed_query.get("returnDate"):
        query["returnDate"] = parsed_query["returnDate"]

    if parsed_query.get("children"):
        query["children"] = parsed_query["children"]

    if parsed_query.get("infants"):
        query["infants"] = parsed_query["infants"]

    if parsed_query.get("airline"):
        query["airline"] = parsed_query["airline"]

    if parsed_query.get("travelClass"):
        query["travelClass"] = parsed_query["travelClass"]

    if parsed_query.get("nonStop") is not None:
        query["nonStop"] = bool(parsed_query["nonStop"])

    if parsed_query.get("currencyCode"):
        query["currencyCode"] = parsed_query["currencyCode"]

    if parsed_query.get("maxPrice"):
        query["maxPrice"] = parsed_query["maxPrice"]

    #  בקשה למזוודה כלולה
    if parsed_query.get("bagsIncluded"):
        query["includedCheckedBagsOnly"] = True

    #  סוג מושב מועדף
    if parsed_query.get("seatType") in ["standard", "extra_legroom"]:
        query["seatType"] = parsed_query["seatType"]  # הערה: רק אם ה־API תומך בזה

    #  אם המשתמש ביקש "טיסה זולה"
    if parsed_query.get("budget") == "cheap" or parsed_query.get("preference") == "cheapest":
        query["sort"] = "price"

    return query


# פונקציה לחיפוש טיסות ב-Amadeus
def search_flights_amadeus(access_token, amadeus_query):
    url = f"{AMADEUS_API_BASE_URL}/v2/shopping/flight-offers"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # בניית רשימת נוסעים
    travelers = []
    for i in range(amadeus_query.get("adults", 1)):
        travelers.append({"id": str(len(travelers) + 1), "travelerType": "ADULT"})
    for i in range(amadeus_query.get("children", 0)):
        travelers.append({"id": str(len(travelers) + 1), "travelerType": "CHILD"})
    for i in range(amadeus_query.get("infants", 0)):
        travelers.append({"id": str(len(travelers) + 1), "travelerType": "HELD_INFANT"})

    # יצירת originDestinations
    origin_destinations = [{
        "id": "1",
        "originLocationCode": amadeus_query["originLocationCode"],
        "destinationLocationCode": amadeus_query["destinationLocationCode"],
        "departureDateTimeRange": {
            "date": amadeus_query["departureDate"]
        }
    }]

    if amadeus_query.get("returnDate"):
        origin_destinations.append({
            "id": "2",
            "originLocationCode": amadeus_query["destinationLocationCode"],
            "destinationLocationCode": amadeus_query["originLocationCode"],
            "departureDateTimeRange": {
                "date": amadeus_query["returnDate"]
            }
        })

    # בסיס ה־payload
    payload = {
        "currencyCode": amadeus_query.get("currencyCode", "USD"),
        "originDestinations": origin_destinations,
        "travelers": travelers,
        "sources": ["GDS"],
        "searchCriteria": {
            "maxFlightOffers": amadeus_query.get("max", 30),
            "flightFilters": {}
        }
    }

    search_criteria = payload["searchCriteria"]

    # מחלקת טיסה
    if amadeus_query.get("travelClass"):
        search_criteria["travelClass"] = amadeus_query["travelClass"]

    # חברת תעופה מועדפת
    if amadeus_query.get("airline"):
        search_criteria["carrierRestrictions"] = {
            "includedCarrierCodes": [amadeus_query["airline"]]
        }

    # טיסה ישירה בלבד (nonStop)
    if amadeus_query.get("nonStop") is not None:
        search_criteria["flightFilters"]["nonStop"] = bool(amadeus_query["nonStop"])

    # סינון לפי כמות עצירות – ללא עצירות בכלל
    if amadeus_query.get("nonStop") is True:
        search_criteria["flightFilters"]["maxNumberOfConnections"] = 0

    # רק טיסות עם כבודה כלולה
    if amadeus_query.get("bagsIncluded"):
        search_criteria["flightFilters"]["includedCheckedBagsOnly"] = True

    # גמישות בתאריכים
    if amadeus_query.get("flexibleDates"):
        search_criteria["dateWindow"] = "PLUS_MINUS_3_DAYS"

    # העדפה למחיר נמוך
    if amadeus_query.get("budget") == "cheap" or amadeus_query.get("preference") == "cheapest":
        search_criteria["sort"] = "price"

    # מחיר מקסימלי
    if amadeus_query.get("maxPrice"):
        payload["maxPrice"] = amadeus_query["maxPrice"]

    #print("\n📤 Payload שנשלח בפועל ל־Amadeus:")
    #print(json.dumps(payload, indent=2, ensure_ascii=False))

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to search flights: {response.status_code}, {response.text}")


def pretty_print_flight_offer(offer) -> str:
    output_str = ""

    price = offer["price"]["grandTotal"]
    currency = offer["price"]["currency"]
    carrier = offer.get("validatingAirlineCodes", ["N/A"])[0]
    duration = offer["itineraries"][0]["duration"].replace("PT", "").replace("H", " שעות ").replace("M", " דקות")
    segments = offer["itineraries"][0]["segments"]

    output_str += "\nטיסת הלוך של חברת:" + "\n" + carrier
    output_str += "-" * 40

    first_seg = segments[0]
    last_seg = segments[-1]

    dep = first_seg["departure"]
    arr = last_seg["arrival"]
    dep_time = dep["at"].replace("T", " ")
    arr_time = arr["at"].replace("T", " ")

    output_str += f"יציאה מ־{dep['iataCode']} (טרמינל {dep.get('terminal', '-')}) בתאריך ושעה: {dep_time}"
    output_str += f"נחיתה ב־{arr['iataCode']} (טרמינל {arr.get('terminal', '-')}) בתאריך ושעה: {arr_time}"
    output_str += f"משך כולל: {duration}"
    output_str += f"מספר עצירות: {len(segments) - 1}"
    output_str += "\n"

    traveler = offer["travelerPricings"][0]
    fare_details = traveler["fareDetailsBySegment"]

    cabin = fare_details[0].get("cabin", "N/A")
    bags = fare_details[0].get("includedCheckedBags", {}).get("quantity", 0)
    carry_on = fare_details[0].get("includedCabinBags", {}).get("quantity", 0)
    amenities = fare_details[0].get("amenities", [])

    meal_included = any(a["amenityType"] == "MEAL" and not a["isChargeable"] for a in amenities)

    output_str += f"כבודה: {bags} מזוודות (יד: {carry_on})"
    output_str += f"ארוחה כלולה: {'כן' if meal_included else 'לא'}"
    output_str += f"מחלקת טיסה: {cabin}"
    output_str += f"מחיר כולל לכל הנוסעים: {price} {currency}"
    output_str += "-" * 40

    return output_str


def pretty_print_all_offers(response, parsed_query):
    offers = response.get("data", [])
    if not offers:
        print("לא נמצאו הצעות טיסה.")
        return

    # סינון מקומי של טיסות ישירות, רק אם המשתמש ביקש זאת
    if parsed_query.get("nonStop") is True:
        offers = [
            offer for offer in offers
            if len(offer["itineraries"][0]["segments"]) == 1
        ]
        if not offers:
            print(" לא נמצאו טיסות ישירות (ללא עצירות) בתאריך המבוקש.")
            return

    for idx, offer in enumerate(offers, start=1):
        print("=" * 60)
        print(f"הצעה מספר {idx}")
        print("=" * 60)
        pretty_print_flight_offer(offer)
        print("\n")


def streamlitGetAllOffersPretty(response, parsed_query) -> str:
    offers = response.get("data", [])
    if not offers:
        return "לא נמצאו הצעות טיסה."

    # סינון מקומי של טיסות ישירות, רק אם המשתמש ביקש זאת
    if parsed_query.get("nonStop") is True:
        offers = [
            offer for offer in offers
            if len(offer["itineraries"][0]["segments"]) == 1
        ]
        if not offers:
            return " לא נמצאו טיסות ישירות (ללא עצירות) בתאריך המבוקש."

    output_str = ""
    limit = 5
    for idx, offer in enumerate(offers, start=1):
        output_str += "=" * 60 + "\n"
        output_str += f"הצעה מספר {idx}" + "\n"
        output_str += "=" * 60 + "\n"
        output_str += pretty_print_flight_offer(offer) + "\n"
        output_str +="\n"
        if limit == idx:
            break

    return output_str


def extract_google_flight_search_data(offer):
    segments = offer["itineraries"][0]["segments"]
    first_segment = segments[0]
    last_segment = segments[-1]
    origin = first_segment["departure"]["iataCode"]
    destination = last_segment["arrival"]["iataCode"]
    departure_date = first_segment["departure"]["at"].split("T")[0]
    return origin, destination, departure_date


def build_google_search_link(origin, destination, date):
    return f"https://www.google.com/travel/flights?q=flights+from+{origin}+to+{destination}+on+{date}"


# פונקציה ראשית שמפיקה את השאילתה המבוקשת
def main():
    print("Welcome to the Smart Flight Search!")
    user_query = input("Please enter your flight search query: \n ")

    try:
        # פירוש שאילתת המשתמש ל-JSON
        parsed_query = interpret_user_query(user_query)
        print("Parsed Query to send to Amadeus API (For Testing):")
        print(json.dumps(parsed_query, indent=4, ensure_ascii=False))

        #משלימה ערכים חסרים
        parsed_query = fill_missing_fields(parsed_query)

        # יצירת השאילתה לפי הפרמטרים של אמדאוס
        amadeus_query = build_amadeus_query(parsed_query)

        # הצגת השאילתה המתואמת לפי אמדאוס
        print("Now you can send this query to Amadeus API:")
        print(json.dumps(amadeus_query, indent=4, ensure_ascii=False))

        # קבלת ה-Access Token
        access_token = get_amadeus_access_token()

        # שליחת השאילתה ל-API של אמדאוס
        flight_results = search_flights_amadeus(access_token, amadeus_query)
        print("Flight Results from Amadeus:")
        #print(json.dumps(flight_results, indent=4, ensure_ascii=False))
        pretty_print_all_offers(flight_results, parsed_query)

        offers = flight_results.get("data", [])
        if not offers:
            print(" לא נמצאו הצעות.")
            return

        # בקשת בחירה מהמשתמש
        while True:
            try:
                choice = int(input(f"\nבחר את מספר ההצעה (1 עד {len(offers)}): "))
                if 1 <= choice <= len(offers):
                    selected_offer = offers[choice - 1]
                    break
                else:
                    print(" מספר לא חוקי. נסה שוב.")
            except ValueError:
                print(" נא להזין מספר תקין.")

        # בניית לינק לגוגל טיסות ופתיחה
        origin, destination, date = extract_google_flight_search_data(selected_offer)
        url = build_google_search_link(origin, destination, date)
        print(" פותח קישור בגוגל טיסות:")
        print(url)
        webbrowser.open(url)

    except Exception as e:
        print({"error": str(e)})


def streamlitMain(user_query: str) -> str:
    print("Welcome to the Smart Flight Search!")

    try:
        # פירוש שאילתת המשתמש ל-JSON
        parsed_query = interpret_user_query(user_query)
        print("Parsed Query to send to Amadeus API (For Testing):")
        print(json.dumps(parsed_query, indent=4, ensure_ascii=False))

        #משלימה ערכים חסרים
        parsed_query = fill_missing_fields(parsed_query)

        # יצירת השאילתה לפי הפרמטרים של אמדאוס
        amadeus_query = build_amadeus_query(parsed_query)

        # הצגת השאילתה המתואמת לפי אמדאוס
        print("Now you can send this query to Amadeus API:")
        print(json.dumps(amadeus_query, indent=4, ensure_ascii=False))

        # קבלת ה-Access Token
        access_token = get_amadeus_access_token()

        # שליחת השאילתה ל-API של אמדאוס
        flight_results = search_flights_amadeus(access_token, amadeus_query)
        print("Flight Results from Amadeus:")
        #print(json.dumps(flight_results, indent=4, ensure_ascii=False))
        result = streamlitGetAllOffersPretty(flight_results, parsed_query)
        
        return result

    except Exception as e:
        print({"error": str(e)})


# הפעלת התוכנית
if __name__ == "__main__":
    main()

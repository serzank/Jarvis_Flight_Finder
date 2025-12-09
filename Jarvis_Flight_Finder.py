import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, timedelta

# --- 1. AYARLAR VE TANIMLAMALAR ---
st.set_page_config(page_title="Jarvis Flight Pro", layout="wide", page_icon="✈️")

# CSS: Buton ve Tablo Düzeni
st.markdown("""
<style>
    .stButton button {
        width: 100%;
        background-color: #FF4B4B;
        color: white;
    }
    div[data-testid="stMetricValue"] {
        font-size: 18px;
    }
</style>
""", unsafe_allow_html=True)

# API Kurulumu
try:
    amadeus = Client(
        client_id='eN67W0VVx8WfcYKAc4GvzJcy3bapkIUe', # Kendi API Keylerinizi buraya da yazabilirsiniz
        client_secret='uZxH10uZmCnhGUiS'
    )
except:
    st.error("API Bağlantı Hatası! Lütfen internet bağlantınızı kontrol edin.")
    st.stop()

# --- VERİTABANI ---
HAVAYOLU_SOZLUGU = {
    "TK": "Turkish Airlines", "VF": "AJet", "AJ": "AJet", "PC": "Pegasus",
    "XQ": "SunExpress", "LH": "Lufthansa", "KL": "KLM", "BA": "British Airways",
    "AF": "Air France", "LO": "LOT Polish", "AZ": "ITA Airways", "FR": "Ryanair",
    "W6": "Wizz Air", "U2": "EasyJet", "VY": "Vueling", "LX": "Swiss",
    "OS": "Austrian", "JU": "Air Serbia", "SN": "Brussels", "A3": "Aegean",
    "IB": "Iberia", "TP": "TAP Portugal", "AY": "Finnair", "SK": "SAS"
}

KALKIS_NOKTALARI = {
    "İstanbul - Tümü": "IST", 
    "İstanbul - Sabiha Gökçen": "SAW",
    "Ankara ESB": "ESB", "İzmir ADB": "ADB", "Antalya AYT": "AYT",
    "Londra LHR": "LHR", "Frankfurt FRA": "FRA" # Test için ek noktalar
}

VARIS_NOKTALARI = {
    "Roma (FCO)": "FCO", "Milano (MXP)": "MXP", "Venedik (VCE)": "VCE",
    "Amsterdam (AMS)": "AMS", "Paris (CDG)": "CDG", "Londra (LHR)": "LHR",
    "Berlin (BER)": "BER", "Münih (MUC)": "MUC", "Frankfurt (FRA)": "FRA",
    "Barselona (BCN)": "BCN", "Madrid (MAD)": "MAD", "Viyana (VIE)": "VIE",
    "New York (JFK)": "JFK", "Dubai (DXB)": "DXB"
}

# --- 2. FONKSİYONLAR ---

def generate_skyscanner_link(origin, dest, date_str):
    """
    Kullanıcıyı o uçuşu satın alabileceği Skyscanner sayfasına yönlendirir.
    Format: https://www.skyscanner.com.tr/transport/flights/{origin}/{dest}/{yymmdd}
    """
    clean_date = date_str.replace("-", "")[2:] # 2025-12-05 -> 251205 formatı
    return f"https://www.skyscanner.com.tr/transport/flights/{origin.lower()}/{dest.lower()}/{clean_date}"

def get_flights(origin, dest, date_go, non_stop):
    """
    Amadeus API Sorgusu
    """
    try:
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=dest,
            departureDate=date_go.strftime("%Y-%m-%d"),
            adults=1,
            max=10,
            nonStop=str(non_stop).lower(), # true/false
            currencyCode="EUR"
        )
        return response.data
    except ResponseError as error:
        st.error(f"API Hatası: {error}")
        return []

def parse_data(offers):
    parsed_list = []
    for offer in offers:
        try:
            # Temel Bilgiler
            itinerary = offer['itineraries'][0]['segments']
            price = float(offer['price']['total'])
            currency = offer['price']['currency']
            
            # Havayolu İsmi
            carrier_code = itinerary[0]['carrierCode']
            airline_name = HAVAYOLU_SOZLUGU.get(carrier_code, carrier_code)
            
            # Saatler
            dep_time = itinerary[0]['departure']['at']
            arr_time = itinerary[-1]['arrival']['at']
            
            # Aktarma Durumu
            stops = len(itinerary) - 1
            type_txt = "Direkt" if stops == 0 else f"{stops} Aktarma"
            
            parsed_list.append({
                "Havayolu": airline_name,
                "Kalkış": itinerary[0]['departure']['iataCode'],
                "Varış": itinerary[-1]['arrival']['iataCode'],
                "Saat": f"{dep_time.split('T')[1][:5]} -> {arr_time.split('T')[1][:5]}",
                "Tip": type_txt,
                "Fiyat": price,
                "Para": currency,
                "Tarih_Raw": dep_time.split('T')[0] # Link üretimi için
            })
        except:
            continue
    return parsed_list

# --- 3. ARAYÜZ ---

with st.sidebar:
    st.header("🛫 Uçuş Planlayıcı")
    
    # LİSTEDEN SEÇİM (İsteğiniz üzerine)
    kalkis_key = st.selectbox("Nereden", list(KALKIS_NOKTALARI.keys()))
    varis_key = st.selectbox("Nereye", list(VARIS_NOKTALARI.keys()), index=0)
    
    # Kodları Sözlükten Çekme
    origin_code = KALKIS_NOKTALARI[kalkis_key]
    dest_code = VARIS_NOKTALARI[varis_key]
    
    st.divider()
    
    tarih = st.date_input("Gidiş Tarihi", min_value=date.today())
    
    # AKTARMA SEÇENEĞİ (İsteğiniz üzerine)
    aktarma_tercihi = st.radio("Uçuş Tipi", ["Tümü", "Sadece Direkt Uçuşlar"])
    is_direct = True if aktarma_tercihi == "Sadece Direkt Uçuşlar" else False
    
    btn_ara = st.button("Uçuşları Listele", type="primary")

# --- 4. SONUÇ EKRANI ---

st.title(f"✈️ {origin_code} ➔ {dest_code}")
st.caption(f"{tarih.strftime('%d %B %Y')} tarihindeki uçuşlar listeleniyor.")

if btn_ara:
    with st.spinner("Veritabanı taranıyor..."):
        raw_data = get_flights(origin_code, dest_code, tarih, is_direct)
        
        if raw_data:
            clean_data = parse_data(raw_data)
            df = pd.DataFrame(clean_data).sort_values("Fiyat")
            
            st.success(f"{len(df)} adet uçuş bulundu.")
            
            # KART GÖRÜNÜMÜ & SATIN ALMA LİNKİ
            for index, row in df.iterrows():
                # Link Oluşturma
                buy_link = generate_skyscanner_link(origin_code, dest_code, row['Tarih_Raw'])
                
                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 1.5, 1.5])
                    
                    # 1. Kolon: Havayolu
                    c1.markdown(f"**{row['Havayolu']}**")
                    c1.caption(row['Tip'])
                    
                    # 2. Kolon: Rota
                    c2.markdown(f"{row['Kalkış']} ➝ {row['Varış']}")
                    
                    # 3. Kolon: Saat
                    c3.markdown(f"⏰ {row['Saat']}")
                    
                    # 4. Kolon: Fiyat
                    c4.markdown(f"#### {int(row['Fiyat'])} {row['Para']}")
                    
                    # 5. Kolon: BUTON (Satın Alma Sayfasına Yönlendirir)
                    c5.link_button("Bilete Git 🔗", buy_link)
                    
        else:
            st.warning("Aradığınız kriterlere uygun uçuş bulunamadı.")
            st.info("İpucu: 'Sadece Direkt' seçeneğini kaldırarak veya tarihi değiştirerek tekrar deneyin.")

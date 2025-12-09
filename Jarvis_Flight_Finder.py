import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, timedelta

# --- 1. AYARLAR ---
st.set_page_config(page_title="Jarvis Flight v11 (Strict Mode)", layout="wide", page_icon="✈️")

# CSS: Buton ve Tasarım
st.markdown("""
<style>
    .stButton button {
        width: 100%;
        background-color: #0e1117; 
        color: #d0d0d0;
        border: 1px solid #333;
        border-radius: 8px;
        transition: all 0.3s;
    }
    .stButton button:hover {
        background-color: #262730;
        border-color: #005EB8;
        color: white;
    }
    div[data-testid="stMetricValue"] {
        font-size: 18px;
    }
</style>
""", unsafe_allow_html=True)

# API Bağlantısı
try:
    amadeus = Client(
        client_id='eN67W0VVx8WfcYKAc4GvzJcy3bapkIUe',
        client_secret='uZxH10uZmCnhGUiS'
    )
except:
    st.error("Sistem Hatası: API bağlantısı kurulamadı.")
    st.stop()

# --- VERİTABANI ---
KALKIS_NOKTALARI = {
    "İstanbul - İGA (IST)": "IST", 
    "İstanbul - Sabiha Gökçen (SAW)": "SAW",
    "Ankara (ESB)": "ESB", 
    "İzmir (ADB)": "ADB", 
    "Antalya (AYT)": "AYT"
}

VARIS_NOKTALARI = {
    "Roma (FCO)": "FCO", "Milano (MXP)": "MXP", "Venedik (VCE)": "VCE",
    "Amsterdam (AMS)": "AMS", "Paris (CDG)": "CDG", "Londra (LHR)": "LHR",
    "Londra (LGW)": "LGW", "Berlin (BER)": "BER", "Münih (MUC)": "MUC",
    "Frankfurt (FRA)": "FRA", "Barselona (BCN)": "BCN", "Madrid (MAD)": "MAD",
    "Viyana (VIE)": "VIE", "New York (JFK)": "JFK", "Dubai (DXB)": "DXB",
    "Bakü (GYD)": "GYD"
}

HAVAYOLU_SOZLUGU = {
    "TK": "Turkish Airlines", "VF": "AJet", "AJ": "AJet", "PC": "Pegasus",
    "XQ": "SunExpress", "LH": "Lufthansa", "KL": "KLM", "BA": "British Airways",
    "AF": "Air France", "LO": "LOT", "AZ": "ITA", "FR": "Ryanair",
    "W6": "Wizz", "U2": "EasyJet", "LX": "Swiss", "OS": "Austrian"
}

# --- 2. FONKSİYONLAR ---

def generate_skyscanner_link(origin, dest, dep_date, ret_date):
    d_str = dep_date.replace("-", "")[2:]
    r_str = ret_date.replace("-", "")[2:]
    return f"https://www.skyscanner.com.tr/transport/flights/{origin.lower()}/{dest.lower()}/{d_str}/{r_str}"

def get_flights(origin, dest, dep_date, ret_date, non_stop):
    try:
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=dest,
            departureDate=dep_date.strftime("%Y-%m-%d"),
            returnDate=ret_date.strftime("%Y-%m-%d"),
            adults=1,
            max=15, # Daha fazla veri çekip filtreleyeceğiz
            nonStop=str(non_stop).lower(),
            currencyCode="EUR"
        )
        return response.data
    except ResponseError:
        return []

def parse_data(offers, requested_origin):
    """
    Veriyi işlerken İSTENEN havalimanı ile GELEN havalimanını kıyaslar.
    Eşleşmiyorsa veriyi çöpe atar.
    """
    parsed_list = []
    
    for offer in offers:
        try:
            # --- 1. GÜVENLİK KONTROLÜ (STRICT FILTER) ---
            # API bazen IST isteyince SAW da gönderebilir ("İstanbul" olarak algılayıp).
            # Bunu manuel olarak engelliyoruz.
            it_out = offer['itineraries'][0]['segments']
            real_origin = it_out[0]['departure']['iataCode']
            
            if real_origin != requested_origin:
                continue # Bu satırı atla, listeye ekleme!

            # --- 2. VERİ ÇEKME ---
            it_in = offer['itineraries'][1]['segments']
            price = float(offer['price']['total'])
            currency = offer['price']['currency']
            
            carrier = it_out[0]['carrierCode']
            airline = HAVAYOLU_SOZLUGU.get(carrier, carrier)
            
            dep_time = it_out[0]['departure']['at'].split('T')[1][:5]
            arr_time = it_out[-1]['arrival']['at'].split('T')[1][:5]
            
            ret_dep_time = it_in[0]['departure']['at'].split('T')[1][:5]
            ret_arr_time = it_in[-1]['arrival']['at'].split('T')[1][:5]
            
            stops_out = len(it_out) - 1
            type_txt = "Direkt" if stops_out == 0 else f"{stops_out} Aktarma"
            
            parsed_list.append({
                "Havayolu": airline,
                "Rota": f"{real_origin} ↔ {it_out[-1]['arrival']['iataCode']}",
                "Saat_Gidis": f"{dep_time} - {arr_time}",
                "Saat_Donus": f"{ret_dep_time} - {ret_arr_time}",
                "Tip": type_txt,
                "Fiyat": price,
                "Para": currency,
                "Date_Raw_Dep": offer['itineraries'][0]['segments'][0]['departure']['at'].split('T')[0],
                "Date_Raw_Ret": offer['itineraries'][1]['segments'][0]['departure']['at'].split('T')[0]
            })
        except:
            continue
            
    return parsed_list

# --- 3. ARAYÜZ ---

with st.sidebar:
    st.header("🛫 Jarvis Flight | Strict Mode")
    
    # Rota Seçimi
    kalkis_key = st.selectbox("Kalkış", list(KALKIS_NOKTALARI.keys()))
    varis_key = st.selectbox("Varış", list(VARIS_NOKTALARI.keys()), index=0)
    
    origin_code = KALKIS_NOKTALARI[kalkis_key]
    dest_code = VARIS_NOKTALARI[varis_key]
    
    st.write("---")
    
    # Tarih Seçimi
    col1, col2 = st.columns(2)
    with col1:
        date_dep = st.date_input("Gidiş", min_value=date.today() + timedelta(days=1))
    with col2:
        date_ret = st.date_input("Dönüş", min_value=date_dep + timedelta(days=2))
        
    only_direct = st.checkbox("Sadece Direkt", value=True)
    
    st.write("---")
    btn_ara = st.button("Uçuş Bul", type="primary")

# --- 4. SONUÇ EKRANI ---

st.subheader(f"Uçuş Sonuçları: {origin_code} ➔ {dest_code}")

if btn_ara:
    with st.spinner(f"{kalkis_key} kalkışlı uçuşlar filtreleniyor..."):
        # API Sorgusu
        raw_results = get_flights(origin_code, dest_code, date_dep, date_ret, only_direct)
        
        # Ayrıştırma ve Katı Filtreleme
        clean_data = parse_data(raw_results, origin_code) 
        
        if clean_data:
            df = pd.DataFrame(clean_data).sort_values("Fiyat")
            
            # Sonuç Kartları
            for index, row in df.iterrows():
                link = generate_skyscanner_link(origin_code, dest_code, row['Date_Raw_Dep'], row['Date_Raw_Ret'])
                
                with st.container(border=True):
                    c1, c2, c3, c4 = st.columns([1.5, 2, 2, 1.5])
                    
                    # Kolon 1: Havayolu
                    c1.markdown(f"**{row['Havayolu']}**")
                    c1.caption(row['Tip'])
                    
                    # Kolon 2: Saatler
                    c2.markdown(f"🛫 {row['Saat_Gidis']}")
                    c2.markdown(f"🛬 {row['Saat_Donus']}")
                    
                    # Kolon 3: Fiyat
                    c3.markdown(f"### {int(row['Fiyat'])} {row['Para']}")
                    
                    # Kolon 4: Aksiyon
                    c4.link_button("Satın Al 🔗", link)
                    
            st.success(f"{len(df)} uygun uçuş listelendi.")
        else:
            st.warning("Uçuş bulunamadı.")
            st.markdown(f"""
            **Olası Sebepler:**
            1. **{origin_code}** kalkışlı direkt uçuş olmayabilir (Örn: Pegasus genellikle SAW kullanır, İGA'dan çıkmaz).
            2. Seçilen tarihlerde doluluk olabilir.
            3. 'Sadece Direkt' filtresini kaldırıp tekrar deneyebilirsiniz.
            """)

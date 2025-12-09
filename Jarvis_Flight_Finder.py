import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, datetime

# --- 1. SİSTEM YAPILANDIRMASI ---
st.set_page_config(page_title="Jarvis Deep Seeker", layout="wide", page_icon="✈️")

# CSS: Kart Görünümü için Ufak Makyaj
st.markdown("""
<style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #ff4b4b;
    }
    [data-testid="stHeader"] {display: none;}
</style>
""", unsafe_allow_html=True)

# API Bağlantısı (Sabit)
try:
    amadeus = Client(
        client_id='eN67W0VVx8WfcYKAc4GvzJcy3bapkIUe',
        client_secret='uZxH10uZmCnhGUiS'
    )
except Exception as e:
    st.error(f"API Bağlantı Hatası: {e}")
    st.stop()

# --- 2. FONKSİYONLAR ---

def get_flight_data(origin, destination, depart_date, return_date):
    """
    Amadeus'a en saf haliyle sorgu atar. Filtrelemez.
    """
    try:
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=destination,
            departureDate=depart_date,
            returnDate=return_date,
            adults=1,
            max=10,  # Maksimum 10 sonuç getir
            currencyCode="EUR"
        )
        return response.data
    except ResponseError as error:
        # Hata detayını terminale basar, kullanıcıya boş liste döner
        print(error)
        return None

def parse_flight(offer):
    """
    Gelen karmaşık JSON verisini temiz bir sözlüğe çevirir.
    """
    try:
        # Fiyat
        price = float(offer['price']['total'])
        currency = offer['price']['currency']
        
        # Gidiş Bacağı
        itinerary_out = offer['itineraries'][0]['segments']
        dep_code = itinerary_out[0]['departure']['iataCode']
        arr_code = itinerary_out[-1]['arrival']['iataCode']
        dep_time = itinerary_out[0]['departure']['at']
        carrier = itinerary_out[0]['carrierCode']
        
        # Dönüş Bacağı
        itinerary_in = offer['itineraries'][1]['segments']
        ret_dep_time = itinerary_in[0]['departure']['at']
        
        # Süreler ve Aktarma Bilgisi
        stops = len(itinerary_out) - 1
        stop_txt = "Direkt" if stops == 0 else f"{stops} Aktarma"
        
        return {
            "Havayolu": carrier,
            "Kalkış": dep_code,
            "Varış": arr_code,
            "Gidiş Tarihi": dep_time.replace("T", " ")[:16],
            "Dönüş Tarihi": ret_dep_time.replace("T", " ")[:16],
            "Tip": stop_txt,
            "Fiyat": price,
            "Para Birimi": currency
        }
    except Exception as e:
        return None

# --- 3. ANA ARAYÜZ ---

st.title("🛫 Jarvis Deep Seeker")
st.markdown("Veritabanını doğrudan, filtresiz tarayan saf mod.")

# Üst Bar: Arama Parametreleri
with st.container(border=True):
    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1])
    
    origin = c1.text_input("Nereden (Kod)", value="IST", max_chars=3).upper()
    dest = c2.text_input("Nereye (Kod)", value="FCO", max_chars=3).upper()
    
    d_date = c3.date_input("Gidiş", value=date.today() + pd.Timedelta(days=7))
    r_date = c4.date_input("Dönüş", value=date.today() + pd.Timedelta(days=11))
    
    btn_search = c5.button("Uçuş Ara", type="primary", use_container_width=True)

# --- 4. SONUÇ EKRANI ---

if btn_search:
    if not origin or not dest:
        st.warning("Lütfen havalimanı kodlarını girin (Örn: IST, SAW, FCO, LHR)")
    else:
        with st.spinner(f"{origin} -> {dest} rotası taranıyor..."):
            # API Sorgusu
            raw_data = get_flight_data(origin, dest, d_date, r_date)
            
            if raw_data:
                # Veriyi İşle
                clean_data = []
                for offer in raw_data:
                    parsed = parse_flight(offer)
                    if parsed:
                        clean_data.append(parsed)
                
                # Tablo Haline Getir
                df = pd.DataFrame(clean_data)
                df = df.sort_values(by="Fiyat")
                
                st.success(f"Toplam {len(df)} uçuş bulundu.")
                
                # SONUÇLARI KART OLARAK GÖSTER
                for idx, row in df.iterrows():
                    with st.container(border=True):
                        k1, k2, k3, k4 = st.columns([1, 2, 2, 1])
                        
                        k1.metric("Havayolu", row['Havayolu'])
                        k2.metric("Gidiş", f"{row['Kalkış']} ➔ {row['Varış']}", row['Gidiş Tarihi'])
                        k3.metric("Dönüş", "Geri Dönüş", row['Dönüş Tarihi'])
                        k4.metric("Tutar", f"{row['Fiyat']} {row['Para Birimi']}", row['Tip'])
                        
            else:
                st.warning(f"⚠️ Amadeus Sandbox veritabanında {origin}-{dest} arası {d_date} tarihinde uçuş kaydı bulunamadı.")
                st.info("💡 Öneri: Test ortamında genellikle 'LON', 'PAR', 'FRA' gibi çok büyük merkezler veya tarihler +15 gün sonrası daha iyi sonuç verir. IST-LHR veya SAW-BER denemesi yapabilirsiniz.")

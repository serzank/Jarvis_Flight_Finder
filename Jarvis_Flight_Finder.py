import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, timedelta

# --- 1. AYARLAR ---
st.set_page_config(page_title="Jarvis Flight v12 (Unlocked)", layout="wide", page_icon="✈️")

# CSS: Modern Görünüm
st.markdown("""
<style>
    .stButton button {
        width: 100%;
        background-color: #FF4B4B;
        color: white;
        border-radius: 8px;
        font-weight: bold;
    }
    .stContainer {
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 15px;
    }
</style>
""", unsafe_allow_html=True)

# API Kurulumu
try:
    amadeus = Client(
        client_id='eN67W0VVx8WfcYKAc4GvzJcy3bapkIUe',
        client_secret='uZxH10uZmCnhGUiS'
    )
except:
    st.error("API Bağlantı Hatası: İnternet bağlantınızı kontrol edin.")
    st.stop()

# --- SABİTLER ---
KALKIS_NOKTALARI = {
    "İstanbul - İGA (IST)": "IST", 
    "İstanbul - Sabiha Gökçen (SAW)": "SAW",
    "Ankara (ESB)": "ESB", "İzmir (ADB)": "ADB", "Antalya (AYT)": "AYT"
}

VARIS_NOKTALARI = {
    "Roma (FCO)": "FCO", "Milano (MXP)": "MXP", "Venedik (VCE)": "VCE",
    "Amsterdam (AMS)": "AMS", "Paris (CDG)": "CDG", "Londra (LHR)": "LHR",
    "Londra (LGW)": "LGW", "Berlin (BER)": "BER", "Münih (MUC)": "MUC",
    "Frankfurt (FRA)": "FRA", "Barselona (BCN)": "BCN", "Madrid (MAD)": "MAD",
    "Viyana (VIE)": "VIE", "New York (JFK)": "JFK", "Dubai (DXB)": "DXB",
    "Bakü (GYD)": "GYD", "Atina (ATH)": "ATH"
}

# --- 2. FONKSİYONLAR ---

def generate_skyscanner_link(origin, dest, dep_date, ret_date):
    """Bilete Git linki oluşturur"""
    d_str = dep_date.replace("-", "")[2:]
    r_str = ret_date.replace("-", "")[2:]
    return f"https://www.skyscanner.com.tr/transport/flights/{origin.lower()}/{dest.lower()}/{d_str}/{r_str}"

def search_flights_unlocked(origin, dest, dep_date, ret_date, non_stop):
    """
    Kısıtlamasız API Sorgusu
    """
    try:
        # 1. API İSTEĞİ
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=dest,
            departureDate=dep_date.strftime("%Y-%m-%d"),
            returnDate=ret_date.strftime("%Y-%m-%d"),
            adults=1,
            max=20, # Limiti artırdık
            nonStop=str(non_stop).lower(),
            currencyCode="EUR"
        )
        
        # 2. SÖZLÜKLERİ (METADATA) ÇEKME
        # Amadeus bize sadece uçuşları değil, o uçuşlardaki kodların anlamlarını da gönderir.
        # Havayolu isimlerini buradan dinamik alacağız.
        dictionaries = response.result.get('dictionaries', {})
        carriers_dict = dictionaries.get('carriers', {})
        
        return response.data, carriers_dict

    except ResponseError as e:
        return [], {}

def parse_flight_data(offers, carriers_dict, requested_origin):
    parsed_list = []
    
    for offer in offers:
        try:
            # Gidiş Bacağı
            seg_out = offer['itineraries'][0]['segments']
            # Dönüş Bacağı
            seg_in = offer['itineraries'][1]['segments']
            
            # --- STRICT FILTER: İGA İSTENDİYSE SAW GELMESİN ---
            real_origin = seg_out[0]['departure']['iataCode']
            if real_origin != requested_origin:
                continue 

            # Havayolu Kodunu Çözümleme
            carrier_code = seg_out[0]['carrierCode']
            # Sözlükten bak, yoksa kodu yaz (Örn: 'KM' -> 'Air Malta')
            airline_name = carriers_dict.get(carrier_code, carrier_code)
            
            # Saatler
            dep_time = seg_out[0]['departure']['at'].split('T')[1][:5]
            arr_time = seg_out[-1]['arrival']['at'].split('T')[1][:5]
            
            ret_dep = seg_in[0]['departure']['at'].split('T')[1][:5]
            ret_arr = seg_in[-1]['arrival']['at'].split('T')[1][:5]
            
            # Fiyat
            price = float(offer['price']['total'])
            currency = offer['price']['currency']
            
            # Durum
            stops = len(seg_out) - 1
            type_txt = "Direkt" if stops == 0 else f"{stops} Aktarma"

            parsed_list.append({
                "Havayolu": airline_name, # ARTIK TAM İSİM GELİYOR
                "Kod": carrier_code,
                "Rota": f"{real_origin} ↔ {seg_out[-1]['arrival']['iataCode']}",
                "Gidiş Saat": f"{dep_time} - {arr_time}",
                "Dönüş Saat": f"{ret_dep} - {ret_arr}",
                "Tip": type_txt,
                "Fiyat": price,
                "Para": currency,
                "Raw_Date_Dep": offer['itineraries'][0]['segments'][0]['departure']['at'].split('T')[0],
                "Raw_Date_Ret": offer['itineraries'][1]['segments'][0]['departure']['at'].split('T')[0]
            })

        except Exception as e:
            continue
            
    return parsed_list

# --- 3. ARAYÜZ ---

with st.sidebar:
    st.header("🌍 Sınırsız Uçuş Arama")
    
    kalkis_secim = st.selectbox("Kalkış", list(KALKIS_NOKTALARI.keys()))
    varis_secim = st.selectbox("Varış", list(VARIS_NOKTALARI.keys()), index=0)
    
    origin_code = KALKIS_NOKTALARI[kalkis_secim]
    dest_code = VARIS_NOKTALARI[varis_secim]
    
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        d_date = st.date_input("Gidiş", min_value=date.today() + timedelta(days=1))
    with col2:
        r_date = st.date_input("Dönüş", min_value=d_date + timedelta(days=3))
        
    st.divider()
    direct_only = st.checkbox("Sadece Direkt Uçuşlar", value=True)
    
    btn_ara = st.button("UÇUŞLARI GETİR", type="primary")

# --- 4. SONUÇ EKRANI ---

st.subheader(f"🔎 Sonuçlar: {origin_code} ➔ {dest_code}")

if btn_ara:
    with st.spinner("Tüm global veritabanı taranıyor..."):
        # Yeni fonksiyonu çağırıyoruz (Veri + Sözlük döner)
        offers_data, carriers_map = search_flights_unlocked(origin_code, dest_code, d_date, r_date, direct_only)
        
        if offers_data:
            # Veriyi işle (Sözlüğü de gönderiyoruz)
            clean_results = parse_flight_data(offers_data, carriers_map, origin_code)
            
            if clean_results:
                df = pd.DataFrame(clean_results).sort_values("Fiyat")
                
                st.success(f"{len(df)} farklı uçuş seçeneği bulundu.")
                
                for idx, row in df.iterrows():
                    link = generate_skyscanner_link(origin_code, dest_code, row['Raw_Date_Dep'], row['Raw_Date_Ret'])
                    
                    with st.container():
                        c1, c2, c3, c4 = st.columns([2, 2, 1.5, 1.5])
                        
                        # 1. Havayolu İsmi (Dinamik)
                        c1.markdown(f"#### {row['Havayolu']}")
                        c1.caption(f"{row['Tip']} • {row['Kod']}")
                        
                        # 2. Saatler
                        c2.markdown(f"🛫 Gidiş: **{row['Gidiş Saat']}**")
                        c2.markdown(f"🛬 Dönüş: **{row['Dönüş Saat']}**")
                        
                        # 3. Fiyat
                        c3.markdown(f"### {int(row['Fiyat'])} {row['Para']}")
                        
                        # 4. Buton
                        c4.link_button("Satın Al 🔗", link)
            else:
                st.warning(f"{origin_code} kalkışlı, kriterlerinize uygun uçuş verisi filtrelere takıldı.")
                st.info("İpucu: 'Sadece Direkt' seçeneğini kaldırarak aktarmalı uçuşları da görebilirsiniz.")
        else:
            st.error("Uçuş bulunamadı.")
            st.info("Bilgi: Amadeus Test (Sandbox) ortamı sınırlı sayıda havayolu verisi içerir. Eğer gerçek hayatta var olan bir uçuş çıkmıyorsa, sebebi test ortamı kısıtlamasıdır, kod kısıtlaması değil.")

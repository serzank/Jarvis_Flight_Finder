import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, timedelta

# --- 1. AYARLAR ---
st.set_page_config(page_title="Jarvis Flight v15 (Split View)", layout="wide", page_icon="✈️")

# CSS: Tasarım
st.markdown("""
<style>
    .stButton button {
        width: 100%;
        background-color: #005EB8;
        color: white;
        font-weight: bold;
        border-radius: 8px;
    }
    .header-box {
        background-color: #f0f2f6;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
        font-weight: bold;
        margin-bottom: 15px;
        color: #333;
        border: 1px solid #ddd;
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
    st.error("API Hatası: İnternet bağlantınızı kontrol edin.")
    st.stop()

# --- VERİ SETLERİ ---
KALKIS_NOKTALARI = {
    "İstanbul - İGA (IST)": "IST", 
    "İstanbul - Sabiha Gökçen (SAW)": "SAW",
    "Ankara (ESB)": "ESB", "İzmir (ADB)": "ADB", "Antalya (AYT)": "AYT"
}

VARIS_NOKTALARI = {
    "Roma (FCO)": "FCO", "Milano (MXP)": "MXP", "Venedik (VCE)": "VCE",
    "Amsterdam (AMS)": "AMS", "Paris (CDG)": "CDG", "Londra (LHR)": "LHR",
    "Berlin (BER)": "BER", "Münih (MUC)": "MUC", "Frankfurt (FRA)": "FRA",
    "Barselona (BCN)": "BCN", "Madrid (MAD)": "MAD", "Viyana (VIE)": "VIE",
    "New York (JFK)": "JFK", "Dubai (DXB)": "DXB", "Atina (ATH)": "ATH"
}

# --- 2. YARDIMCI FONKSİYONLAR (REVİZE EDİLDİ) ---

def generate_oneway_link(origin, dest, dep_date, carrier_code):
    """
    Skyscanner Tek Yön Linki
    """
    d_str = dep_date.replace("-", "")[2:]
    base_url = f"https://www.skyscanner.com.tr/transport/flights/{origin.lower()}/{dest.lower()}/{d_str}"
    
    if carrier_code:
        return f"{base_url}?airlines={carrier_code}"
    return base_url

def search_oneway(origin, dest, date_travel, direct):
    """
    Tek yönlü arama yapan fonksiyon (Sadece departureDate kullanılır)
    """
    try:
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=dest,
            departureDate=date_travel.strftime("%Y-%m-%d"),
            adults=1,
            max=10, # Her bacak için en iyi 10
            nonStop=str(direct).lower(),
            currencyCode="EUR"
        )
        return response.data, response.result.get('dictionaries', {}).get('carriers', {})
    except ResponseError:
        return [], {}

def parse_results(offers, carriers, req_origin):
    """
    Sonuçları işler (Tek yön mantığına göre revize edildi)
    """
    data = []
    for o in offers:
        try:
            # Tek yön aramada sadece itineraries[0] vardır
            seg = o['itineraries'][0]['segments']
            
            # --- STRICT FILTER ---
            real_origin = seg[0]['departure']['iataCode']
            if real_origin != req_origin:
                continue

            carrier_code = seg[0]['carrierCode']
            airline = carriers.get(carrier_code, carrier_code)
            
            price = float(o['price']['total'])
            currency = o['price']['currency']
            
            # Saatler
            dep_time = seg[0]['departure']['at'].split('T')[1][:5]
            arr_time = seg[-1]['arrival']['at'].split('T')[1][:5]
            
            stops = len(seg) - 1
            tip = "Direkt" if stops == 0 else f"{stops} Aktarma"
            
            data.append({
                "Havayolu": airline,
                "Kod": carrier_code,
                "Rota": f"{real_origin} ➝ {seg[-1]['arrival']['iataCode']}",
                "Saat": f"{dep_time} - {arr_time}",
                "Tip": tip,
                "Fiyat": price,
                "Para": currency,
                "Raw_Date": o['itineraries'][0]['segments'][0]['departure']['at'].split('T')[0]
            })
        except:
            continue
    return data

# --- 3. ARAYÜZ ---

with st.sidebar:
    st.header("✈️ Jarvis Flight Manager")
    
    kalkis = st.selectbox("Kalkış", list(KALKIS_NOKTALARI.keys()))
    varis = st.selectbox("Varış", list(VARIS_NOKTALARI.keys()))
    
    origin_code = KALKIS_NOKTALARI[kalkis]
    dest_code = VARIS_NOKTALARI[varis]
    
    st.divider()
    
    c1, c2 = st.columns(2)
    d_date = c1.date_input("Gidiş", min_value=date.today() + timedelta(days=7))
    r_date = c2.date_input("Dönüş", min_value=d_date + timedelta(days=2))
    
    direct_only = st.checkbox("Sadece Direkt Uçuşlar", value=True)
    
    st.divider()
    btn = st.button("Uçuşları Ayrı Ayrı Bul", type="primary")

# --- 4. SONUÇ EKRANI ---

st.title(f"{origin_code} ↔ {dest_code}")

if btn:
    with st.spinner("Gidiş ve Dönüş veritabanları ayrı ayrı taranıyor..."):
        
        # --- 1. GİDİŞ SORGU (Origin -> Dest) ---
        raw_out, maps_out = search_oneway(origin_code, dest_code, d_date, direct_only)
        results_out = parse_results(raw_out, maps_out, origin_code)
        
        # --- 2. DÖNÜŞ SORGU (Dest -> Origin) ---
        # Burada yönleri ve tarihi değiştiriyoruz
        raw_in, maps_in = search_oneway(dest_code, origin_code, r_date, direct_only)
        # Filtre için req_origin artık dest_code oluyor
        results_in = parse_results(raw_in, maps_in, dest_code) 
        
        # --- EKRANA BASMA (2 KOLON) ---
        col_gidis, col_donus = st.columns(2)
        
        # === SOL SÜTUN: GİDİŞ ===
        with col_gidis:
            st.markdown(f"<div class='header-box'>🛫 GİDİŞ: {origin_code} ➔ {dest_code}<br>{d_date.strftime('%d.%m.%Y')}</div>", unsafe_allow_html=True)
            
            if results_out:
                df_out = pd.DataFrame(results_out).sort_values("Fiyat")
                for i, row in df_out.iterrows():
                    link = generate_oneway_link(origin_code, dest_code, row['Raw_Date'], row['Kod'])
                    with st.container(border=True):
                        c1, c2 = st.columns([2, 1])
                        c1.markdown(f"**{row['Havayolu']}**")
                        c2.markdown(f"**{int(row['Fiyat'])} €**")
                        st.caption(f"{row['Saat']} | {row['Tip']}")
                        st.link_button("Seç ➜", link, use_container_width=True)
            else:
                st.warning("Gidiş uçuşu bulunamadı.")

        # === SAĞ SÜTUN: DÖNÜŞ ===
        with col_donus:
            st.markdown(f"<div class='header-box'>🛬 DÖNÜŞ: {dest_code} ➔ {origin_code}<br>{r_date.strftime('%d.%m.%Y')}</div>", unsafe_allow_html=True)
            
            if results_in:
                df_in = pd.DataFrame(results_in).sort_values("Fiyat")
                for i, row in df_in.iterrows():
                    # Linkte Origin/Dest ters çevrili olmalı
                    link = generate_oneway_link(dest_code, origin_code, row['Raw_Date'], row['Kod'])
                    with st.container(border=True):
                        c1, c2 = st.columns([2, 1])
                        c1.markdown(f"**{row['Havayolu']}**")
                        c2.markdown(f"**{int(row['Fiyat'])} €**")
                        st.caption(f"{row['Saat']} | {row['Tip']}")
                        st.link_button("Seç ➜", link, use_container_width=True)
            else:
                st.warning("Dönüş uçuşu bulunamadı.")

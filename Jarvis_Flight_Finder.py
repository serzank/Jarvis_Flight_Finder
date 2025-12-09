import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, timedelta

# --- 1. AYARLAR ---
st.set_page_config(page_title="Jarvis Flight v14 (Final)", layout="wide", page_icon="✈️")

# CSS: Profesyonel Kart Tasarımı
st.markdown("""
<style>
    .stButton button {
        width: 100%;
        background-color: #005EB8;
        color: white;
        font-weight: bold;
        border-radius: 8px;
    }
    .info-box {
        background-color: #e3f2fd;
        padding: 10px;
        border-radius: 5px;
        border-left: 5px solid #005EB8;
        margin-bottom: 20px;
        font-size: 14px;
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

# --- 2. YARDIMCI FONKSİYONLAR ---

def generate_deeplink(origin, dest, dep_date, ret_date, carrier_code):
    """
    Skyscanner Link Üretici - Havayolu Filtreli
    """
    d_str = dep_date.replace("-", "")[2:]
    r_str = ret_date.replace("-", "")[2:]
    
    base_url = f"https://www.skyscanner.com.tr/transport/flights/{origin.lower()}/{dest.lower()}/{d_str}/{r_str}"
    
    # Eğer havayolu kodu belliyse linke ekle
    if carrier_code:
        return f"{base_url}?airlines={carrier_code}"
    return base_url

def search_amadeus(origin, dest, d_date, r_date, direct):
    try:
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=dest,
            departureDate=d_date.strftime("%Y-%m-%d"),
            returnDate=r_date.strftime("%Y-%m-%d"),
            adults=1,
            max=20,
            nonStop=str(direct).lower(),
            currencyCode="EUR"
        )
        return response.data, response.result.get('dictionaries', {}).get('carriers', {})
    except ResponseError:
        return [], {}

def clean_results(offers, carriers, req_origin):
    data = []
    for o in offers:
        try:
            seg_out = o['itineraries'][0]['segments']
            seg_in = o['itineraries'][1]['segments']
            
            # --- STRICT FILTER ---
            # Kullanıcı IST seçtiyse, API'nin SAW önerilerini sil.
            real_origin = seg_out[0]['departure']['iataCode']
            if real_origin != req_origin:
                continue

            carrier_code = seg_out[0]['carrierCode']
            airline = carriers.get(carrier_code, carrier_code)
            
            price = float(o['price']['total'])
            currency = o['price']['currency']
            
            # Saat Formatlama
            t_out = f"{seg_out[0]['departure']['at'].split('T')[1][:5]} ➝ {seg_out[-1]['arrival']['at'].split('T')[1][:5]}"
            t_in = f"{seg_in[0]['departure']['at'].split('T')[1][:5]} ➝ {seg_in[-1]['arrival']['at'].split('T')[1][:5]}"
            
            stops = len(seg_out) - 1
            tip = "Direkt" if stops == 0 else f"{stops} Aktarma"
            
            data.append({
                "Havayolu": airline,
                "Kod": carrier_code,
                "Rota": f"{real_origin} - {seg_out[-1]['arrival']['iataCode']}",
                "Gidiş": t_out,
                "Dönüş": t_in,
                "Tip": tip,
                "Fiyat": price,
                "Para": currency,
                "Raw_Dep": o['itineraries'][0]['segments'][0]['departure']['at'].split('T')[0],
                "Raw_Ret": o['itineraries'][1]['segments'][0]['departure']['at'].split('T')[0]
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
    r_date = c2.date_input("Dönüş", min_value=d_date + timedelta(days=3))
    
    direct_only = st.checkbox("Sadece Direkt Uçuşlar", value=True)
    
    st.divider()
    btn = st.button("Uçuş Ara", type="primary")

# --- 4. SONUÇ EKRANI ---

st.title(f"{origin_code} ✈ {dest_code}")

# BİLGİLENDİRME KUTUSU (ÖNEMLİ)
st.markdown(f"""
<div class="info-box">
    <b>⚠️ Fiyat Uyarısı (Sandbox Mode):</b><br>
    Şu an geliştirici (Test) modundasınız. Görüntülenen fiyatlar (Örn: 300 EUR), havayolunun geçmiş veritabanından çekilen
    referans fiyatlardır. <b>Canlı biletleme fiyatları (Skyscanner/THY) doluluk oranına göre %30-400 daha yüksek çıkabilir.</b>
    Bu araç rota ve havayolu planlaması için idealdir.
</div>
""", unsafe_allow_html=True)

if btn:
    with st.spinner("Veriler analiz ediliyor..."):
        raw, maps = search_amadeus(origin_code, dest_code, d_date, r_date, direct_only)
        
        if raw:
            results = clean_results(raw, maps, origin_code)
            
            if results:
                df = pd.DataFrame(results).sort_values("Fiyat")
                st.success(f"{len(df)} adet uçuş bulundu.")
                
                for i, row in df.iterrows():
                    link = generate_deeplink(origin_code, dest_code, row['Raw_Dep'], row['Raw_Ret'], row['Kod'])
                    
                    with st.container():
                        col1, col2, col3, col4 = st.columns([2, 2.5, 1.5, 1.5])
                        
                        # Kolon 1: Logo/İsim
                        col1.markdown(f"**{row['Havayolu']}**")
                        col1.caption(f"{row['Tip']} ({row['Kod']})")
                        
                        # Kolon 2: Saatler
                        col2.markdown(f"🛫 {row['Gidiş']}")
                        col2.markdown(f"🛬 {row['Dönüş']}")
                        
                        # Kolon 3: Fiyat (Tahmini)
                        col3.markdown(f"### {int(row['Fiyat'])} €")
                        col3.caption("Referans Fiyat")
                        
                        # Kolon 4: Buton
                        col4.link_button("Fiyatı Doğrula 🔗", link)
            else:
                st.warning(f"{origin_code} kalkışlı ve kriterlere uygun uçuş bulunamadı.")
        else:
            st.error("Veri bulunamadı. (Test ortamı kısıtlaması olabilir, tarihi değiştirip deneyin).")

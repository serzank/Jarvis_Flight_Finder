import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, timedelta

# --- 1. AYARLAR ---
st.set_page_config(page_title="Jarvis Flight v13 (Smart Link)", layout="wide", page_icon="✈️")

# CSS
st.markdown("""
<style>
    .stButton button {
        width: 100%;
        background-color: #005EB8;
        color: white;
        border-radius: 8px;
    }
    .stContainer {
        border: 1px solid #ddd;
        border-radius: 12px;
        padding: 15px;
        background-color: #fff;
    }
</style>
""", unsafe_allow_html=True)

# API
try:
    amadeus = Client(
        client_id='eN67W0VVx8WfcYKAc4GvzJcy3bapkIUe',
        client_secret='uZxH10uZmCnhGUiS'
    )
except:
    st.error("API Hatası.")
    st.stop()

# --- SÖZLÜKLER ---
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

# --- 2. FONKSİYONLAR ---

def generate_smart_link(origin, dest, dep_date, ret_date, carrier_code):
    """
    Skyscanner Linkini oluştururken 'airlines' parametresini ekler.
    Böylece sayfa açılınca sadece o havayolu seçili gelir.
    """
    d_str = dep_date.replace("-", "")[2:]
    r_str = ret_date.replace("-", "")[2:]
    
    # URL'nin sonuna havayolu filtresi ekliyoruz: ?airlines=IATA_KODU
    base_url = f"https://www.skyscanner.com.tr/transport/flights/{origin.lower()}/{dest.lower()}/{d_str}/{r_str}"
    
    # Carrier code varsa filtreye ekle (Örn: AZ -> ITA, TK -> THY)
    if carrier_code:
        return f"{base_url}?airlines={carrier_code}"
    
    return base_url

def search_flights(origin, dest, dep_date, ret_date, non_stop):
    try:
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=origin,
            destinationLocationCode=dest,
            departureDate=dep_date.strftime("%Y-%m-%d"),
            returnDate=ret_date.strftime("%Y-%m-%d"),
            adults=1,
            max=20, 
            nonStop=str(non_stop).lower(),
            currencyCode="EUR"
        )
        
        dictionaries = response.result.get('dictionaries', {})
        carriers_dict = dictionaries.get('carriers', {})
        
        return response.data, carriers_dict

    except ResponseError:
        return [], {}

def parse_flight_data(offers, carriers_dict, requested_origin):
    parsed_list = []
    for offer in offers:
        try:
            seg_out = offer['itineraries'][0]['segments']
            seg_in = offer['itineraries'][1]['segments']
            
            # IST istendi ama SAW geldiyse filtrele
            real_origin = seg_out[0]['departure']['iataCode']
            if real_origin != requested_origin:
                continue 

            carrier_code = seg_out[0]['carrierCode']
            airline_name = carriers_dict.get(carrier_code, carrier_code)
            
            # Saatler
            dep_time = seg_out[0]['departure']['at'].split('T')[1][:5]
            arr_time = seg_out[-1]['arrival']['at'].split('T')[1][:5]
            ret_dep = seg_in[0]['departure']['at'].split('T')[1][:5]
            ret_arr = seg_in[-1]['arrival']['at'].split('T')[1][:5]
            
            price = float(offer['price']['total'])
            currency = offer['price']['currency']
            
            stops = len(seg_out) - 1
            type_txt = "Direkt" if stops == 0 else f"{stops} Aktarma"

            parsed_list.append({
                "Havayolu": airline_name,
                "Kod": carrier_code, # Link için gerekli
                "Rota": f"{real_origin} ↔ {seg_out[-1]['arrival']['iataCode']}",
                "Gidiş Saat": f"{dep_time} - {arr_time}",
                "Dönüş Saat": f"{ret_dep} - {ret_arr}",
                "Tip": type_txt,
                "Fiyat": price,
                "Para": currency,
                "Raw_Date_Dep": offer['itineraries'][0]['segments'][0]['departure']['at'].split('T')[0],
                "Raw_Date_Ret": offer['itineraries'][1]['segments'][0]['departure']['at'].split('T')[0]
            })
        except:
            continue
    return parsed_list

# --- 3. ARAYÜZ ---

with st.sidebar:
    st.header("✈️ Akıllı Uçuş Aracı")
    
    kalkis_secim = st.selectbox("Kalkış", list(KALKIS_NOKTALARI.keys()))
    varis_secim = st.selectbox("Varış", list(VARIS_NOKTALARI.keys()), index=0)
    
    origin_code = KALKIS_NOKTALARI[kalkis_secim]
    dest_code = VARIS_NOKTALARI[varis_secim]
    
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1: d_date = st.date_input("Gidiş", min_value=date.today() + timedelta(days=1))
    with c2: r_date = st.date_input("Dönüş", min_value=d_date + timedelta(days=3))
        
    direct_only = st.checkbox("Sadece Direkt", value=True)
    btn_ara = st.button("Uçuşları Listele", type="primary")

# --- 4. SONUÇLAR ---

st.subheader(f"{origin_code} ➔ {dest_code} | {d_date.strftime('%d.%m')} - {r_date.strftime('%d.%m')}")

if btn_ara:
    with st.spinner("Veriler taranıyor..."):
        offers, maps = search_flights(origin_code, dest_code, d_date, r_date, direct_only)
        
        if offers:
            df_list = parse_flight_data(offers, maps, origin_code)
            
            if df_list:
                df = pd.DataFrame(df_list).sort_values("Fiyat")
                st.info(f"Toplam {len(df)} seçenek bulundu.")
                
                for idx, row in df.iterrows():
                    # Linke artık Havayolu Kodunu (row['Kod']) gönderiyoruz
                    smart_link = generate_smart_link(
                        origin_code, 
                        dest_code, 
                        row['Raw_Date_Dep'], 
                        row['Raw_Date_Ret'],
                        row['Kod'] # <--- ÖNEMLİ: Linki filtreleyen kod
                    )
                    
                    with st.container():
                        col1, col2, col3, col4 = st.columns([2, 2, 1.5, 1.5])
                        
                        col1.markdown(f"**{row['Havayolu']}**")
                        col1.caption(f"{row['Tip']} ({row['Kod']})")
                        
                        col2.markdown(f"🛫 {row['Gidiş Saat']}")
                        col2.markdown(f"🛬 {row['Dönüş Saat']}")
                        
                        col3.markdown(f"### {int(row['Fiyat'])} {row['Para']}")
                        
                        # Buton artık daha dürüst
                        col4.link_button("Bileti Gör 🔗", smart_link)
            else:
                st.warning("Filtrelere uygun uçuş yok. (İGA/SAW ayrımına dikkat edin).")
        else:
            st.error("Uçuş verisi alınamadı.")

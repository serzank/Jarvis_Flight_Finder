import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, timedelta

# --- 1. AYARLAR ---
st.set_page_config(page_title="Jarvis Flight v10", layout="wide", page_icon="✈️")

# CSS: Buton ve Tablo
st.markdown("""
<style>
    .stButton button {
        width: 100%;
        background-color: #005EB8; /* İGA Mavisi */
        color: white;
        border-radius: 8px;
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
    st.error("API Hatası: Bağlantı kurulamadı.")
    st.stop()

# --- VERİTABANI ---
# İGA ve SAW ayrımı netleştirildi
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
    """
    Skyscanner Link Formatı: origin/dest/yymmdd/yymmdd
    Örn: ist/fco/251201/251205
    """
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
            max=10,
            nonStop=str(non_stop).lower(),
            currencyCode="EUR"
        )
        return response.data
    except ResponseError as e:
        st.error(f"Sorgu Hatası: {e}")
        return []

def parse_data(offers):
    parsed_list = []
    for offer in offers:
        try:
            # Gidiş Detayları
            it_out = offer['itineraries'][0]['segments']
            # Dönüş Detayları
            it_in = offer['itineraries'][1]['segments']
            
            # Fiyat
            price = float(offer['price']['total'])
            currency = offer['price']['currency']
            
            # Havayolu
            carrier = it_out[0]['carrierCode']
            airline = HAVAYOLU_SOZLUGU.get(carrier, carrier)
            
            # Saatler
            dep_time = it_out[0]['departure']['at'].split('T')[1][:5]
            arr_time = it_out[-1]['arrival']['at'].split('T')[1][:5]
            
            # Dönüş Saatleri
            ret_dep_time = it_in[0]['departure']['at'].split('T')[1][:5]
            ret_arr_time = it_in[-1]['arrival']['at'].split('T')[1][:5]
            
            # Aktarma Bilgisi
            stops_out = len(it_out) - 1
            type_txt = "Direkt" if stops_out == 0 else f"{stops_out} Aktarma"
            
            parsed_list.append({
                "Havayolu": airline,
                "Rota": f"{it_out[0]['departure']['iataCode']} ↔ {it_out[-1]['arrival']['iataCode']}",
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
    st.title("🛫 Uçuş Planlayıcı")
    
    # Rota Seçimi
    kalkis_key = st.selectbox("Kalkış", list(KALKIS_NOKTALARI.keys()))
    varis_key = st.selectbox("Varış", list(VARIS_NOKTALARI.keys()), index=0)
    
    origin_code = KALKIS_NOKTALARI[kalkis_key]
    dest_code = VARIS_NOKTALARI[varis_key]
    
    st.divider()
    
    # TARİH SEÇİMİ (Çift Tarih)
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        date_dep = st.date_input("Gidiş Tarihi", min_value=date.today())
    with col_d2:
        date_ret = st.date_input("Dönüş Tarihi", min_value=date_dep + timedelta(days=1), value=date_dep + timedelta(days=4))
        
    st.divider()
    
    # Filtreler
    only_direct = st.checkbox("Sadece Direkt Uçuşlar", value=True)
    
    btn_ara = st.button("Uçuşları Listele", type="primary")

# --- 4. SONUÇLAR ---

st.subheader(f"✈️ {kalkis_key.split('(')[0]} ➔ {varis_key.split('(')[0]}")
st.caption(f"Tarih Aralığı: {date_dep.strftime('%d.%m.%Y')} - {date_ret.strftime('%d.%m.%Y')}")

if btn_ara:
    with st.spinner("En uygun biletler taranıyor..."):
        if date_ret <= date_dep:
            st.error("Hata: Dönüş tarihi gidiş tarihinden önce olamaz.")
        else:
            raw_results = get_flights(origin_code, dest_code, date_dep, date_ret, only_direct)
            
            if raw_results:
                clean_data = parse_data(raw_results)
                df = pd.DataFrame(clean_data).sort_values("Fiyat")
                
                st.success(f"{len(df)} adet uçuş bulundu.")
                
                for index, row in df.iterrows():
                    # Link oluştururken hem gidiş hem dönüş tarihini kullanıyoruz
                    link = generate_skyscanner_link(origin_code, dest_code, row['Date_Raw_Dep'], row['Date_Raw_Ret'])
                    
                    with st.container(border=True):
                        c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 1.5, 1.5])
                        
                        # Havayolu & Tip
                        c1.markdown(f"**{row['Havayolu']}**")
                        c1.caption(row['Tip'])
                        
                        # Gidiş Bilgisi
                        c2.markdown("🛫 **Gidiş**")
                        c2.write(row['Saat_Gidis'])
                        
                        # Dönüş Bilgisi
                        c3.markdown("🛬 **Dönüş**")
                        c3.write(row['Saat_Donus'])
                        
                        # Fiyat
                        c4.markdown(f"#### {int(row['Fiyat'])} {row['Para']}")
                        
                        # Buton
                        c5.link_button("Bilete Git 🔗", link)
            else:
                st.warning("Bu tarih ve rota için uygun uçuş bulunamadı.")
                st.info("İpucu: 'Sadece Direkt' seçeneğini kaldırarak tekrar deneyin.")

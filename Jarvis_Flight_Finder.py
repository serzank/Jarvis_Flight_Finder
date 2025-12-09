import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, timedelta
import concurrent.futures

# --- 1. AYARLAR VE API ---
amadeus = Client(
    client_id='eN67W0VVx8WfcYKAc4GvzJcy3bapkIUe',
    client_secret='uZxH10uZmCnhGUiS'
)

# Havayolu Kodları Sözlüğü (Daha şık görünmesi için)
HAVAYOLU_ISIMLERI = {
    "TK": "Turkish Airlines",
    "AJ": "AJet",
    "PC": "Pegasus",
    "LH": "Lufthansa",
    "KL": "KLM Royal Dutch",
    "BA": "British Airways",
    "AF": "Air France",
    "LO": "LOT Polish",
    "AZ": "ITA Airways",
    "FR": "Ryanair",
    "W6": "Wizz Air",
    "U2": "EasyJet"
}

# --- 2. VERİTABANI ---
KALKIS_NOKTALARI = {
    "İstanbul - Avrupa (IST)": "IST",
    "İstanbul - Sabiha Gökçen (SAW)": "SAW",
    "İzmir (ADB)": "ADB",
    "Ankara (ESB)": "ESB",
}

ULKE_SEHIR_VERITABANI = {
    "İtalya": {"Roma": "FCO", "Milano": "MXP", "Venedik": "VCE"},
    "Hollanda": {"Amsterdam": "AMS", "Eindhoven": "EIN"},
    "Polonya": {"Varşova": "WAW", "Krakow": "KRK"},
    "Birleşik Krallık": {"Londra": "LON", "Manchester": "MAN"},
    "Danimarka": {"Kopenhag": "CPH"},
    "Bulgaristan": {"Sofya": "SOF"},
    "Almanya": {"Berlin": "BER", "Münih": "MUC", "Frankfurt": "FRA"},
    "Fransa": {"Paris": "PAR", "Nice": "NCE"},
}

# --- 3. FONKSİYONLAR ---

def tekil_arama_yap(parametreler):
    kalkis, varis, gidis_tarihi, seyahat_suresi = parametreler
    donus_tarihi = gidis_tarihi + timedelta(days=seyahat_suresi)
    try:
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=kalkis,
            destinationLocationCode=varis,
            departureDate=gidis_tarihi.strftime("%Y-%m-%d"),
            returnDate=donus_tarihi.strftime("%Y-%m-%d"),
            adults=1,
            max=1 
        )
        return response.data, varis
    except ResponseError:
        return [], varis

@st.cache_data(ttl=600, show_spinner=False)
def toplu_arama_motoru(kalkis_kodu, hedef_sehirler, baslangic_tarihi, arama_araligi, seyahat_suresi):
    tum_gorevler = []
    for sehir_adi, iata_kodu in hedef_sehirler.items():
        for i in range(1, arama_araligi + 1):
            tarih = baslangic_tarihi + timedelta(days=i)
            tum_gorevler.append((kalkis_kodu, iata_kodu, tarih, seyahat_suresi))
    
    islenmis_sonuclar = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_search = {executor.submit(tekil_arama_yap, p): p for p in tum_gorevler}
        for future in concurrent.futures.as_completed(future_to_search):
            ham_veri, ilgili_iata = future.result()
            sehir_ismi = [k for k, v in hedef_sehirler.items() if v == ilgili_iata][0]
            if ham_veri:
                temiz_veri = veriyi_isleme(ham_veri, sehir_ismi)
                islenmis_sonuclar.extend(temiz_veri)
    return islenmis_sonuclar

def veriyi_isleme(ham_veri, sehir_adi):
    islenmis_liste = []
    for ucus in ham_veri:
        try:
            fiyat = float(ucus['price']['total'])
            para_birimi = ucus['price']['currency']
            
            # Gidiş Detayları
            seg_gidis = ucus['itineraries'][0]['segments'][0]
            g_tarih_ham = seg_gidis['departure']['at']
            g_saat = g_tarih_ham.split('T')[1][:5]
            g_tarih = g_tarih_ham.split('T')[0]
            
            # Dönüş Detayları
            seg_donus = ucus['itineraries'][1]['segments'][0]
            d_tarih_ham = seg_donus['departure']['at']
            d_saat = d_tarih_ham.split('T')[1][:5]
            d_tarih = d_tarih_ham.split('T')[0]
            
            havayolu_kod = seg_gidis['carrierCode']
            havayolu_ad = HAVAYOLU_ISIMLERI.get(havayolu_kod, havayolu_kod) # Sözlükten bulamazsa kodu yaz
            
            # Aktarma Kontrol
            g_aktarma = len(ucus['itineraries'][0]['segments']) - 1
            d_aktarma = len(ucus['itineraries'][1]['segments']) - 1
            aktarma_durumu = "Direkt Uçuş" if (g_aktarma + d_aktarma) == 0 else f"{g_aktarma+d_aktarma} Aktarma"

            islenmis_liste.append({
                "Varış Şehri": sehir_adi,
                "Varış Kodu": seg_gidis['arrival']['iataCode'],
                "Kalkış Kodu": seg_gidis['departure']['iataCode'],
                "Fiyat": fiyat,
                "Para Birimi": para_birimi,
                "Havayolu": havayolu_ad,
                "Havayolu Kodu": havayolu_kod,
                "Uçuş Tipi": aktarma_durumu,
                "Gidiş Tarihi": g_tarih,
                "Gidiş Saati": g_saat,
                "Dönüş Tarihi": d_tarih,
                "Dönüş Saati": d_saat
            })
        except:
            continue
    return islenmis_liste

# --- 4. BOARDING PASS GÖRSELLEŞTİRME (HTML/CSS) ---
def bilet_olustur(bilet):
    # Havayoluna göre renk belirleme (Opsiyonel estetik dokunuş)
    renk = "#d32f2f" if bilet['Havayolu Kodu'] == "TK" else "#0056b3" # TK ise kırmızı, diğerleri mavi
    
    html_kod = f"""
    <style>
        .ticket-container {{
            background-color: white;
            border-radius: 16px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            display: flex;
            margin-bottom: 20px;
            overflow: hidden;
            border: 1px solid #e0e0e0;
            font-family: 'Arial', sans-serif;
        }}
        .ticket-left {{
            background-color: {renk};
            color: white;
            padding: 20px;
            width: 30%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            border-right: 2px dashed white;
            position: relative;
        }}
        .ticket-right {{
            padding: 20px;
            width: 70%;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        .route {{ font-size: 24px; font-weight: bold; margin-bottom: 5px; }}
        .date-large {{ font-size: 18px; opacity: 0.9; }}
        .info-row {{ display: flex; justify-content: space-between; margin-bottom: 10px; }}
        .info-label {{ font-size: 12px; color: #757575; text-transform: uppercase; }}
        .info-value {{ font-size: 16px; font-weight: bold; color: #212121; }}
        .price-tag {{ 
            background-color: #e8f5e9; 
            color: #2e7d32; 
            padding: 5px 15px; 
            border-radius: 20px; 
            font-weight: bold; 
            font-size: 18px;
            border: 1px solid #c8e6c9;
        }}
        .airline-logo {{ font-size: 14px; font-weight: bold; opacity: 0.8; letter-spacing: 1px; }}
    </style>
    
    <div class="ticket-container">
        <div class="ticket-left">
            <div class="airline-logo">{bilet['Havayolu']}</div>
            <div style="font-size: 40px;">✈</div>
            <div class="route">{bilet['Kalkış Kodu']} <br>⬇<br> {bilet['Varış Kodu']}</div>
        </div>
        <div class="ticket-right">
            <div class="info-row">
                <div>
                    <div class="info-label">Gidiş Tarihi</div>
                    <div class="info-value">{bilet['Gidiş Tarihi']} 🕒 {bilet['Gidiş Saati']}</div>
                </div>
                <div>
                    <div class="info-label">Dönüş Tarihi</div>
                    <div class="info-value">{bilet['Dönüş Tarihi']} 🕒 {bilet['Dönüş Saati']}</div>
                </div>
            </div>
            <div class="info-row">
                <div>
                    <div class="info-label">Uçuş Tipi</div>
                    <div class="info-value">{bilet['Uçuş Tipi']}</div>
                </div>
                <div>
                    <div class="info-label">Yolcu</div>
                    <div class="info-value">1 Yetişkin</div>
                </div>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px; border-top: 1px solid #eee; padding-top: 10px;">
                <div style="font-family: 'Courier New', monospace; font-size: 12px; color: #aaa;">
                    PNR: JARVIS-X{int(bilet['Fiyat'])}
                </div>
                <div class="price-tag">{bilet['Fiyat']:.2f} {bilet['Para Birimi']}</div>
            </div>
        </div>
    </div>
    """
    st.markdown(html_kod, unsafe_allow_html=True)

# --- 5. ARAYÜZ ---
st.set_page_config(page_title="Jarvis Flight Design", layout="centered")

st.title("🎫 Uçuş Kartları")
st.caption("Sir, favori rotalarınız için en iyi biletler tasarım formatında hazırlandı.")

with st.sidebar:
    st.header("⚙️ Parametreler")
    kalkis_secim = st.selectbox("Kalkış", list(KALKIS_NOKTALARI.keys()))
    kalkis_code = KALKIS_NOKTALARI[kalkis_secim]
    
    secilen_ulkeler = st.multiselect("Ülke", list(ULKE_SEHIR_VERITABANI.keys()), default=["İtalya"])
    
    hedef_sehirler = {}
    for ulke in secilen_ulkeler:
        hedef_sehirler.update(ULKE_SEHIR_VERITABANI[ulke])
        
    seyahat_suresi = st.slider("Seyahat (Gün)", 2, 10, 4)
    arama_araligi = st.slider("Tarama Aralığı (Gün)", 3, 30, 7)
    
    st.markdown("---")
    arama_butonu = st.button("Biletleri Oluştur", type="primary")

if arama_butonu:
    with st.spinner("Biletler tasarlanıyor..."):
        sonuclar = toplu_arama_motoru(kalkis_code, hedef_sehirler, date.today(), arama_araligi, seyahat_suresi)
    
    if sonuclar:
        df = pd.DataFrame(sonuclar).sort_values(by="Fiyat")
        st.success(f"{len(df)} uçuş bulundu. En iyi 10 seçenek listeleniyor:")
        
        # En ucuz 10 bileti kart olarak bas
        for index, row in df.head(10).iterrows():
            bilet_olustur(row)
            
    else:
        st.error("Kriterlere uygun uçuş bulunamadı.")

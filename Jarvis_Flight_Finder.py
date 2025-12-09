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

# Havayolu Kodları
HAVAYOLU_ISIMLERI = {
    "TK": "Turkish Airlines", "VF": "AJet", "AJ": "AJet", "PC": "Pegasus",
    "XQ": "SunExpress", "LH": "Lufthansa", "KL": "KLM", "BA": "British Airways",
    "AF": "Air France", "LO": "LOT", "AZ": "ITA Airways", "FR": "Ryanair",
    "W6": "Wizz Air", "U2": "EasyJet", "VY": "Vueling", "LX": "Swiss",
    "OS": "Austrian", "JU": "Air Serbia", "SN": "Brussels", "A3": "Aegean",
    "IB": "Iberia", "TP": "TAP Portugal", "AY": "Finnair", "SK": "SAS",
    "BT": "Air Baltic", "OU": "Croatia Airlines", "KM": "Air Malta"
}

KALKIS_NOKTALARI = {
    "İstanbul - Avrupa (IST)": "IST", 
    "İstanbul - Sabiha Gökçen (SAW)": "SAW",
    "İzmir (ADB)": "ADB", "Ankara (ESB)": "ESB", "Antalya (AYT)": "AYT"
}

ULKE_SEHIR_VERITABANI = {
    "İtalya": {"Roma": "FCO", "Milano": "MXP", "Venedik": "VCE", "Napoli": "NAP"},
    "Hollanda": {"Amsterdam": "AMS", "Rotterdam": "RTM", "Eindhoven": "EIN"},
    "Polonya": {"Varşova": "WAW", "Krakow": "KRK", "Gdansk": "GDN"},
    "İngiltere": {"Londra": "LON", "Manchester": "MAN"},
    "Almanya": {"Berlin": "BER", "Münih": "MUC", "Frankfurt": "FRA", "Köln": "CGN"},
    "Fransa": {"Paris": "PAR", "Nice": "NCE"},
    "İspanya": {"Barselona": "BCN", "Madrid": "MAD"},
    "Danimarka": {"Kopenhag": "CPH"},
    "Bulgaristan": {"Sofya": "SOF"},
}

# --- 2. FONKSİYONLAR ---

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
            max=10 
        )
        return response.data, varis
    except ResponseError:
        return [], varis

@st.cache_data(ttl=300, show_spinner=False)
def hizli_arama_motoru(kalkis_kodu, hedef_sehirler_dict, baslangic_tarihi, arama_araligi, seyahat_suresi):
    tum_gorevler = []
    
    for sehir_adi, iata_kodu in hedef_sehirler_dict.items():
        for i in range(1, arama_araligi + 1):
            tarih = baslangic_tarihi + timedelta(days=i)
            tum_gorevler.append((kalkis_kodu, iata_kodu, tarih, seyahat_suresi))
            
    islenmis_sonuclar = []
    toplam_gorev = len(tum_gorevler)
    
    bar = st.progress(0)
    status = st.empty()
    tamamlanan = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_to_search = {executor.submit(tekil_arama_yap, p): p for p in tum_gorevler}
        
        for future in concurrent.futures.as_completed(future_to_search):
            ham_veriler, ilgili_iata = future.result()
            sehir_ismi = [k for k, v in hedef_sehirler_dict.items() if v == ilgili_iata][0]
            
            if ham_veriler:
                for ucus in ham_veriler:
                    try:
                        itinerary_gidis = ucus['itineraries'][0]
                        segmentler_gidis = itinerary_gidis['segments']
                        ilk_nokta = segmentler_gidis[0]['departure']['iataCode']
                        son_nokta = segmentler_gidis[-1]['arrival']['iataCode']
                        
                        if ilk_nokta != kalkis_kodu: continue

                        itinerary_donus = ucus['itineraries'][1]
                        segmentler_donus = itinerary_donus['segments']
                        
                        tarih_g_full = segmentler_gidis[0]['departure']['at']
                        tarih_d_full = segmentler_donus[0]['departure']['at']
                        
                        fiyat = float(ucus['price']['total'])
                        para = ucus['price']['currency']
                        
                        h_kod = segmentler_gidis[0]['carrierCode']
                        h_ad = HAVAYOLU_ISIMLERI.get(h_kod, h_kod)
                        
                        toplam_bacak = len(segmentler_gidis) + len(segmentler_donus)
                        tip = "Direkt" if toplam_bacak == 2 else f"{toplam_bacak-2} Aktarma"

                        islenmis_sonuclar.append({
                            "Şehir": sehir_ismi,
                            "Kalkış": ilk_nokta,
                            "Varış": son_nokta,
                            "Fiyat": fiyat,
                            "Para": para,
                            "Havayolu": h_ad,
                            "Kod": h_kod,
                            "Tip": tip,
                            "G_Tarih": tarih_g_full.split('T')[0],
                            "G_Saat": tarih_g_full.split('T')[1][:5],
                            "D_Tarih": tarih_d_full.split('T')[0],
                            "D_Saat": tarih_d_full.split('T')[1][:5]
                        })
                        break 
                    except: continue
            
            tamamlanan += 1
            bar.progress(tamamlanan / toplam_gorev)
            status.text(f"Veritabanları Taranıyor... %{int((tamamlanan/toplam_gorev)*100)}")
            
    bar.empty()
    status.empty()
    return islenmis_sonuclar

def bilet_kart_ciz(bilet):
    # Renk Ayarları
    renk_map = {
        "TK": "#C8102E", "VF": "#005EB8", "AJ": "#005EB8", "PC": "#F4B323",
        "LH": "#FAB415", "BA": "#01295F", "KL": "#00A1DE", "AF": "#002157"
    }
    renk = renk_map.get(bilet['Kod'], "#546E7A")
    yazi_rengi = "#333" if bilet['Kod'] in ["PC", "LH"] else "#fff"
    
    fiyat_str = f"{int(bilet['Fiyat']):,}".replace(",", ".")

    # HTML KODU (BOŞLUKSUZ VE TEMİZ)
    html_code = f"""
<div style="font-family: 'Arial', sans-serif; background: #fff; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); margin-bottom: 20px; border: 1px solid #eee; overflow: hidden; display: flex;">
    <div style="background: {renk}; width: 50px; display: flex; align-items: center; justify-content: center;">
        <div style="color: {yazi_rengi}; font-weight: 900; font-size: 16px; transform: rotate(-90deg); white-space: nowrap;">{bilet['Kod']}</div>
    </div>
    <div style="flex: 1; padding: 15px 20px;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 15px; border-bottom: 1px solid #f0f0f0; padding-bottom: 10px;">
            <span style="font-weight: 700; color: #333; font-size: 16px;">{bilet['Havayolu']}</span>
            <span style="background: #e3f2fd; color: #1565c0; padding: 2px 10px; border-radius: 12px; font-size: 11px; font-weight: 700;">{bilet['Tip']}</span>
        </div>
        <div style="display: flex; align-items: center; justify-content: space-between;">
            <div style="text-align: left;">
                <div style="font-size: 24px; font-weight: 800; color: #222;">{bilet['G_Saat']}</div>
                <div style="font-size: 12px; color: #777;">{bilet['Kalkış']} • {bilet['G_Tarih']}</div>
            </div>
            <div style="color: #ddd; font-size: 20px;">✈</div>
            <div style="text-align: right;">
                <div style="font-size: 24px; font-weight: 800; color: #222;">{bilet['D_Saat']}</div>
                <div style="font-size: 12px; color: #777;">{bilet['Varış']} • {bilet['D_Tarih']}</div>
            </div>
        </div>
    </div>
    <div style="width: 120px; background: #f9f9f9; display: flex; flex-direction: column; align-items: center; justify-content: center; border-left: 1px dashed #ccc;">
        <div style="font-size: 11px; color: #888;">TOPLAM</div>
        <div style="font-size: 22px; font-weight: 900; color: #2e7d32;">{fiyat_str}</div>
        <div style="font-size: 13px; font-weight: 700; color: #2e7d32;">{bilet['Para']}</div>
    </div>
</div>
"""
    st.markdown(html_code, unsafe_allow_html=True)

# --- 3. ARAYÜZ ---
st.set_page_config(page_title="Jarvis Air v5.1", layout="centered", page_icon="✈️")

st.markdown("<h1 style='text-align: center;'>✈ Jarvis Flight Manager</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>Tüm veritabanları taranarak en optimize rotalar oluşturuluyor.</p>", unsafe_allow_html=True)

with st.sidebar:
    st.header("Parametreler")
    kalkis_secim = st.selectbox("Kalkış", list(KALKIS_NOKTALARI.keys()))
    kalkis_code = KALKIS_NOKTALARI[kalkis_secim]
    
    st.markdown("---")
    secilen_ulkeler = st.multiselect("Bölge", list(ULKE_SEHIR_VERITABANI.keys()), default=["İtalya"])
    olasi = {}
    for u in secilen_ulkeler: olasi.update(ULKE_SEHIR_VERITABANI[u])
    secilen_sehirler = st.multiselect("Şehir", list(olasi.keys()), default=list(olasi.keys())[:3])
    hedef_dict = {k: v for k, v in olasi.items() if k in secilen_sehirler}

    st.markdown("---")
    sure = st.slider("Gün", 2, 10, 4)
    aralik = st.slider("Tarama Aralığı", 3, 30, 7)
    btn = st.button("UÇUŞLARI GETİR", type="primary")

# --- 4. AKIŞ ---
if btn:
    if not hedef_dict:
        st.warning("Şehir seçiniz.")
    else:
        sonuclar = hizli_arama_motoru(kalkis_code, hedef_dict, date.today(), aralik, sure)
        if sonuclar:
            df = pd.DataFrame(sonuclar).sort_values(by="Fiyat")
            st.success(f"İşlem Tamamlandı: {len(df)} adet uygun rota bulundu.")
            for i, row in df.head(10).iterrows():
                bilet_kart_ciz(row)
        else:
            st.error("Uçuş bulunamadı. Kriterleri değiştirin.")

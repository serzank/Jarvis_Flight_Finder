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

# Havayolu İsimleri
HAVAYOLU_ISIMLERI = {
    "TK": "Turkish Airlines", "VF": "AJet", "AJ": "AJet", "PC": "Pegasus",
    "XQ": "SunExpress", "LH": "Lufthansa", "KL": "KLM", "BA": "British Airways",
    "AF": "Air France", "LO": "LOT", "AZ": "ITA", "FR": "Ryanair",
    "W6": "Wizz", "U2": "EasyJet", "VY": "Vueling", "LX": "Swiss",
    "OS": "Austrian", "JU": "Air Serbia", "SN": "Brussels", "A3": "Aegean"
}

KALKIS_NOKTALARI = {
    "İstanbul - Avrupa (IST)": "IST", 
    "İstanbul - Sabiha Gökçen (SAW)": "SAW",
    "İzmir (ADB)": "ADB", "Ankara (ESB)": "ESB", "Antalya (AYT)": "AYT"
}

ULKE_SEHIR_VERITABANI = {
    "İtalya": {"Roma": "FCO", "Milano": "MXP", "Venedik": "VCE"},
    "Hollanda": {"Amsterdam": "AMS", "Rotterdam": "RTM", "Eindhoven": "EIN"},
    "Polonya": {"Varşova": "WAW", "Krakow": "KRK"},
    "İngiltere": {"Londra": "LON", "Manchester": "MAN"},
    "Almanya": {"Berlin": "BER", "Münih": "MUC", "Frankfurt": "FRA"},
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
            max=5 # Hızlı yanıt için limit
        )
        return response.data, varis
    except:
        return [], varis

@st.cache_data(ttl=300, show_spinner=False)
def hizli_arama_motoru(kalkis_kodu, hedef_sehirler_dict, baslangic_tarihi, arama_araligi, seyahat_suresi, sadece_direkt):
    tum_gorevler = []
    
    # Görev listesi oluştur
    for sehir_adi, iata_kodu in hedef_sehirler_dict.items():
        for i in range(1, arama_araligi + 1):
            tarih = baslangic_tarihi + timedelta(days=i)
            tum_gorevler.append((kalkis_kodu, iata_kodu, tarih, seyahat_suresi))
            
    islenmis_sonuclar = []
    
    # Progress Bar
    bar = st.progress(0)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_search = {executor.submit(tekil_arama_yap, p): p for p in tum_gorevler}
        tamamlanan = 0
        
        for future in concurrent.futures.as_completed(future_to_search):
            tamamlanan += 1
            bar.progress(tamamlanan / len(tum_gorevler))
            
            ham_veriler, ilgili_iata = future.result()
            sehir_ismi = [k for k, v in hedef_sehirler_dict.items() if v == ilgili_iata][0]
            
            if ham_veriler:
                for ucus in ham_veriler:
                    try:
                        # Gidiş
                        gidis_seg = ucus['itineraries'][0]['segments']
                        ilk_nokta = gidis_seg[0]['departure']['iataCode']
                        
                        # Filtre: Kalkış Noktası Kontrolü
                        if ilk_nokta != kalkis_kodu: continue

                        # Dönüş
                        donus_seg = ucus['itineraries'][1]['segments']
                        
                        # Direkt Kontrolü
                        toplam_bacak = len(gidis_seg) + len(donus_seg)
                        is_direct = (toplam_bacak == 2)
                        if sadece_direkt and not is_direct: continue
                        
                        # Verileri Çek
                        fiyat = float(ucus['price']['total'])
                        para = ucus['price']['currency']
                        h_kod = gidis_seg[0]['carrierCode']
                        havayolu = HAVAYOLU_ISIMLERI.get(h_kod, h_kod)
                        
                        # Saatler
                        g_saat = gidis_seg[0]['departure']['at'].split('T')[1][:5]
                        d_saat = donus_seg[0]['departure']['at'].split('T')[1][:5]
                        g_tarih = gidis_seg[0]['departure']['at'].split('T')[0]

                        islenmis_sonuclar.append({
                            "Havayolu": havayolu,
                            "Rota": f"{sehir_ismi} ({ilgili_iata})",
                            "Tip": "Direkt" if is_direct else "Aktarmalı",
                            "Tarih": g_tarih,
                            "Gidiş Saati": g_saat,
                            "Dönüş Saati": d_saat,
                            "Fiyat": fiyat,
                            "Para Birimi": para
                        })
                        break # O gün için en ucuzunu al çık
                    except: continue

    bar.empty()
    return islenmis_sonuclar

# --- 3. ARAYÜZ ---
st.set_page_config(page_title="Jarvis Simple Air", layout="wide")

st.header("✈️ Jarvis Flight | Simple Mode")

# Sidebar
with st.sidebar:
    kalkis_secim = st.selectbox("Kalkış", list(KALKIS_NOKTALARI.keys()))
    kalkis_code = KALKIS_NOKTALARI[kalkis_secim]
    
    st.write("---")
    
    secilen_ulkeler = st.multiselect("Bölge", list(ULKE_SEHIR_VERITABANI.keys()), default=["İtalya"])
    olasi = {}
    for u in secilen_ulkeler: olasi.update(ULKE_SEHIR_VERITABANI[u])
    secilen_sehirler = st.multiselect("Şehirler", list(olasi.keys()), default=list(olasi.keys())[:2])
    
    hedef_dict = {k: v for k, v in olasi.items() if k in secilen_sehirler}
    
    st.write("---")
    
    col1, col2 = st.columns(2)
    with col1: sure = st.number_input("Kalınacak Gün", 2, 10, 3)
    with col2: aralik = st.number_input("Tarama Aralığı", 2, 20, 5)
    
    sadece_direkt = st.checkbox("Sadece Direkt", value=True)
    
    btn = st.button("Listele", type="primary", use_container_width=True)

# Main Area
if btn:
    if hedef_dict:
        veriler = hizli_arama_motoru(kalkis_code, hedef_dict, date.today(), aralik, sure, sadece_direkt)
        
        if veriler:
            df = pd.DataFrame(veriler).sort_values("Fiyat")
            
            # Tablo Gösterimi (Simple Interface)
            for index, row in df.iterrows():
                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1.5])
                    
                    c1.markdown(f"**{row['Havayolu']}**")
                    c1.caption(row['Tip'])
                    
                    c2.markdown(f"📍 **{row['Rota']}**")
                    c2.caption(f"{row['Tarih']}")
                    
                    c3.markdown(f"🛫 Gidiş: **{row['Gidiş Saati']}**")
                    c4.markdown(f"🛬 Dönüş: **{row['Dönüş Saati']}**")
                    
                    fiyat_txt = f"{int(row['Fiyat']):,} {row['Para Birimi']}".replace(",", ".")
                    c5.markdown(f"#### {fiyat_txt}")
                    
        else:
            # Sessiz mod: Hata mesajı yok, sadece bilgi.
            st.info("Kriterlerinize uygun güncel veri düşmedi. Tarih veya rotayı genişletebilirsiniz.")
    else:
        st.warning("Lütfen şehir seçin.")

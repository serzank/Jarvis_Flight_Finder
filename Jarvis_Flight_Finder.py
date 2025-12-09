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

# Havayolu İsim Sözlüğü
HAVAYOLU_ISIMLERI = {
    "TK": "Turkish Airlines", "VF": "AJet", "AJ": "AJet", "PC": "Pegasus Airlines",
    "XQ": "SunExpress", "LH": "Lufthansa", "KL": "KLM Royal Dutch", "BA": "British Airways",
    "AF": "Air France", "LO": "LOT Polish", "AZ": "ITA Airways", "FR": "Ryanair",
    "W6": "Wizz Air", "U2": "EasyJet", "VY": "Vueling", "LX": "Swiss Int.",
    "OS": "Austrian Airlines", "JU": "Air Serbia", "SN": "Brussels Airlines", "A3": "Aegean",
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
        # API her zaman karışık getirsin, biz Python tarafında filtreleyeceğiz
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
def hizli_arama_motoru(kalkis_kodu, hedef_sehirler_dict, baslangic_tarihi, arama_araligi, seyahat_suresi, sadece_direkt):
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
                        # --- Gidiş Analizi ---
                        itinerary_gidis = ucus['itineraries'][0]
                        segmentler_gidis = itinerary_gidis['segments']
                        ilk_nokta = segmentler_gidis[0]['departure']['iataCode']
                        son_nokta = segmentler_gidis[-1]['arrival']['iataCode']
                        
                        # Filtre: Yanlış havalimanı kontrolü
                        if ilk_nokta != kalkis_kodu: continue

                        # --- Dönüş Analizi ---
                        itinerary_donus = ucus['itineraries'][1]
                        segmentler_donus = itinerary_donus['segments']
                        
                        # --- Direkt Uçuş Kontrolü ---
                        toplam_bacak = len(segmentler_gidis) + len(segmentler_donus)
                        is_direct = (toplam_bacak == 2)
                        
                        # EĞER kullanıcı "Sadece Direkt" seçtiyse ve uçuş direkt değilse -> ATLA
                        if sadece_direkt and not is_direct:
                            continue
                        
                        tip = "Direkt Uçuş" if is_direct else f"{toplam_bacak-2} Aktarma"

                        # Tarihler
                        tarih_g_kalkis = segmentler_gidis[0]['departure']['at']
                        tarih_g_varis = segmentler_gidis[-1]['arrival']['at']
                        
                        tarih_d_kalkis = segmentler_donus[0]['departure']['at']
                        tarih_d_varis = segmentler_donus[-1]['arrival']['at']
                        
                        # Fiyat ve İsim
                        fiyat = float(ucus['price']['total'])
                        para = ucus['price']['currency']
                        h_kod = segmentler_gidis[0]['carrierCode']
                        h_ad = HAVAYOLU_ISIMLERI.get(h_kod, h_kod) # İsim yoksa kodu kullan ama genelde isim gelir

                        islenmis_sonuclar.append({
                            "Şehir": sehir_ismi,
                            "Kalkış": ilk_nokta,
                            "Varış": son_nokta,
                            "Fiyat": fiyat,
                            "Para": para,
                            "Havayolu": h_ad,
                            "Kod": h_kod,
                            "Tip": tip,
                            # Gidiş Bilgileri
                            "G_Tarih": tarih_g_kalkis.split('T')[0],
                            "G_Saat_Kalkis": tarih_g_kalkis.split('T')[1][:5],
                            "G_Saat_Varis": tarih_g_varis.split('T')[1][:5],
                            # Dönüş Bilgileri
                            "D_Tarih": tarih_d_kalkis.split('T')[0],
                            "D_Saat_Kalkis": tarih_d_kalkis.split('T')[1][:5],
                            "D_Saat_Varis": tarih_d_varis.split('T')[1][:5]
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
    renk = renk_map.get(bilet['Kod'], "#607d8b")
    fiyat_str = f"{int(bilet['Fiyat']):,}".replace(",", ".")

    # HTML Tasarım - İKİ AYRI SÜTUN (Split View)
    html_code = f"""
    <div style="font-family: 'Segoe UI', sans-serif; background: white; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.08); margin-bottom: 25px; border: 1px solid #e0e0e0; overflow: hidden;">
        
        <div style="background: {renk}; padding: 10px 20px; color: white; display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: 700; font-size: 16px; letter-spacing: 0.5px;">{bilet['Havayolu']}</span>
            <span style="background: rgba(255,255,255,0.2); padding: 2px 10px; border-radius: 12px; font-size: 11px;">{bilet['Tip']}</span>
        </div>

        <div style="display: flex; flex-direction: row; padding: 20px;">
            
            <div style="flex: 1; padding-right: 15px; border-right: 1px dashed #ccc;">
                <div style="font-size: 11px; color: #999; font-weight: 700; margin-bottom: 5px;">GİDİŞ ✈</div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="text-align: left;">
                        <div style="font-size: 20px; font-weight: 800; color: #333;">{bilet['G_Saat_Kalkis']}</div>
                        <div style="font-size: 12px; color: #666;">{bilet['Kalkış']}</div>
                    </div>
                    <div style="color: #ddd; font-size: 14px;">➝</div>
                    <div style="text-align: right;">
                        <div style="font-size: 20px; font-weight: 800; color: #333;">{bilet['G_Saat_Varis']}</div>
                        <div style="font-size: 12px; color: #666;">{bilet['Varış']}</div>
                    </div>
                </div>
                <div style="font-size: 12px; color: #888; margin-top: 5px;">{bilet['G_Tarih']}</div>
            </div>

            <div style="flex: 1; padding-left: 15px;">
                <div style="font-size: 11px; color: #999; font-weight: 700; margin-bottom: 5px;">DÖNÜŞ ✈</div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="text-align: left;">
                        <div style="font-size: 20px; font-weight: 800; color: #333;">{bilet['D_Saat_Kalkis']}</div>
                        <div style="font-size: 12px; color: #666;">{bilet['Varış']}</div>
                    </div>
                    <div style="color: #ddd; font-size: 14px;">➝</div>
                    <div style="text-align: right;">
                        <div style="font-size: 20px; font-weight: 800; color: #333;">{bilet['D_Saat_Varis']}</div>
                        <div style="font-size: 12px; color: #666;">{bilet['Kalkış']}</div>
                    </div>
                </div>
                <div style="font-size: 12px; color: #888; margin-top: 5px;">{bilet['D_Tarih']}</div>
            </div>

            <div style="width: 100px; display: flex; flex-direction: column; justify-content: center; align-items: center; padding-left: 15px; border-left: 1px solid #eee;">
                <div style="font-size: 20px; font-weight: 900; color: #2e7d32;">{fiyat_str}</div>
                <div style="font-size: 12px; font-weight: 600; color: #2e7d32;">{bilet['Para']}</div>
            </div>

        </div>
    </div>
    """
    st.markdown(html_code, unsafe_allow_html=True)

# --- 3. ARAYÜZ ---
st.set_page_config(page_title="Jarvis Air v6.0", layout="centered", page_icon="✈️")

st.markdown("<h1 style='text-align: center;'>✈ Jarvis Flight Manager</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #666;'>Tüm veritabanları taranarak en optimize rotalar oluşturuluyor.</p>", unsafe_allow_html=True)

with st.sidebar:
    st.header("Parametreler")
    kalkis_secim = st.selectbox("Kalkış", list(KALKIS_NOKTALARI.keys()))
    kalkis_code = KALKIS_NOKTALARI[kalkis_secim]
    
    # YENİ EKLENEN FİLTRE
    sadece_direkt = st.checkbox("Sadece Direkt Uçuşlar", value=True)
    
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
        # sadece_direkt parametresi fonksiyona eklendi
        sonuclar = hizli_arama_motoru(kalkis_code, hedef_dict, date.today(), aralik, sure, sadece_direkt)
        
        if sonuclar:
            df = pd.DataFrame(sonuclar).sort_values(by="Fiyat")
            st.success(f"İşlem Tamamlandı: {len(df)} adet uygun rota bulundu.")
            for i, row in df.head(10).iterrows():
                bilet_kart_ciz(row)
        else:
            st.error("Uçuş bulunamadı. Kriterleri değiştirin.")

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

# Havayolu Kodları Sözlüğü (Genişletilmiş ve Güncellenmiş)
HAVAYOLU_ISIMLERI = {
    "TK": "Turkish Airlines", 
    "VF": "AJet", 
    "AJ": "AJet",
    "PC": "Pegasus Airlines", 
    "XQ": "SunExpress",
    "HV": "Transavia",
    "XC": "Corendon",
    "LH": "Lufthansa",
    "KL": "KLM Royal Dutch", 
    "BA": "British Airways", 
    "AF": "Air France", 
    "LO": "LOT Polish Airlines",
    "AZ": "ITA Airways", 
    "FR": "Ryanair", 
    "W6": "Wizz Air", 
    "U2": "EasyJet",
    "VY": "Vueling",
    "LX": "Swiss International",
    "OS": "Austrian Airlines",
    "JU": "Air Serbia",
    "SN": "Brussels Airlines",
    "A3": "Aegean Airlines",
    "IB": "Iberia",
    "TP": "TAP Air Portugal",
    "AY": "Finnair",
    "SK": "SAS Scandinavian"
}

# Veritabanı
KALKIS_NOKTALARI = {
    "İstanbul - Avrupa (IST)": "IST", 
    "İstanbul - Sabiha Gökçen (SAW)": "SAW",
    "İzmir (ADB)": "ADB", 
    "Ankara (ESB)": "ESB", 
    "Antalya (AYT)": "AYT"
}

ULKE_SEHIR_VERITABANI = {
    "İtalya": {"Roma": "FCO", "Milano": "MXP", "Venedik": "VCE", "Napoli": "NAP"},
    "Hollanda": {"Amsterdam": "AMS", "Rotterdam": "RTM", "Eindhoven": "EIN"},
    "Polonya": {"Varşova": "WAW", "Krakow": "KRK", "Gdansk": "GDN"},
    "İngiltere": {"Londra (Tümü)": "LON", "Manchester": "MAN"},
    "Almanya": {"Berlin": "BER", "Münih": "MUC", "Frankfurt": "FRA", "Köln": "CGN"},
    "Fransa": {"Paris": "PAR", "Nice": "NCE"},
    "İspanya": {"Barselona": "BCN", "Madrid": "MAD"},
    "Danimarka": {"Kopenhag": "CPH"},
    "Bulgaristan": {"Sofya": "SOF"},
}

# --- 2. FONKSİYONLAR ---

def tekil_arama_yap(parametreler):
    """Tekil API sorgusu."""
    kalkis, varis, gidis_tarihi, seyahat_suresi = parametreler
    donus_tarihi = gidis_tarihi + timedelta(days=seyahat_suresi)
    try:
        # returnDate parametresi olduğu için API otomatik olarak Gidiş-Dönüş arar
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

@st.cache_data(ttl=300, show_spinner=False)
def hizli_arama_motoru(kalkis_kodu, hedef_sehirler_dict, baslangic_tarihi, arama_araligi, seyahat_suresi):
    """Paralel İşlem Motoru"""
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_search = {executor.submit(tekil_arama_yap, p): p for p in tum_gorevler}
        
        for future in concurrent.futures.as_completed(future_to_search):
            ham_veri, ilgili_iata = future.result()
            
            sehir_ismi = [k for k, v in hedef_sehirler_dict.items() if v == ilgili_iata][0]
            
            if ham_veri:
                ucus = ham_veri[0]
                try:
                    fiyat = float(ucus['price']['total'])
                    para = ucus['price']['currency']
                    
                    seg_g = ucus['itineraries'][0]['segments'][0]
                    g_kod = seg_g['departure']['iataCode']
                    v_kod = seg_g['arrival']['iataCode']
                    tarih_g = seg_g['departure']['at']
                    
                    seg_d = ucus['itineraries'][1]['segments'][0]
                    tarih_d = seg_d['departure']['at']
                    
                    h_kod = seg_g['carrierCode']
                    # SÖZLÜKTEN TAM İSMİ ÇEKME İŞLEMİ:
                    h_ad = HAVAYOLU_ISIMLERI.get(h_kod, h_kod) # Bulamazsa kodu yazar ama genelde bulur
                    
                    toplam_seg = len(ucus['itineraries'][0]['segments']) + len(ucus['itineraries'][1]['segments'])
                    tip = "Direkt" if toplam_seg == 2 else "Aktarmalı"

                    islenmis_sonuclar.append({
                        "Şehir": sehir_ismi,
                        "Kalkış": g_kod,
                        "Varış": v_kod,
                        "Fiyat": fiyat,
                        "Para": para,
                        "Havayolu": h_ad,
                        "Kod": h_kod,
                        "Tip": tip,
                        "G_Tarih": tarih_g.split('T')[0],
                        "G_Saat": tarih_g.split('T')[1][:5],
                        "D_Tarih": tarih_d.split('T')[0],
                        "D_Saat": tarih_d.split('T')[1][:5]
                    })
                except:
                    pass
            
            tamamlanan += 1
            bar.progress(tamamlanan / toplam_gorev)
            status.text(f"Taranıyor: {tamamlanan}/{toplam_gorev} uçuş...")
            
    bar.empty()
    status.empty()
    return islenmis_sonuclar

def bilet_kart_ciz(bilet):
    # Renk ayarları
    if bilet['Kod'] == "TK":
        renk = "#d32f2f" # Kırmızı (THY)
    elif bilet['Kod'] in ["VF", "AJ", "PC"]:
        renk = "#fbc02d" # Sarı (Pegasus/AJet)
        yazi_rengi = "#333"
    else:
        renk = "#1976d2" # Mavi (Diğer)
        yazi_rengi = renk
        
    html = f"""
    <div style="background: white; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); margin-bottom: 20px; display: flex; overflow: hidden; font-family: 'Segoe UI', sans-serif; border: 1px solid #e0e0e0;">
        <div style="background: {renk}; width: 12px;"></div>
        <div style="padding: 20px; flex-grow: 1;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid #f0f0f0; padding-bottom: 10px;">
                <span style="font-weight: 800; color: #333; font-size: 18px; letter-spacing: 0.5px;">
                    <span style="color: {yazi_rengi}; margin-right:8px;">✈</span> {bilet['Havayolu']}
                </span>
                <div style="text-align: right;">
                    <span style="background: #e3f2fd; color: #1565c0; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; margin-right: 5px;">GİDİŞ - DÖNÜŞ</span>
                    <span style="background: #f1f8e9; color: #33691e; padding: 4px 10px; border-radius: 15px; font-size: 12px; font-weight: bold; border: 1px solid #c5e1a5;">{bilet['Tip']}</span>
                </div>
            </div>
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div style="text-align: left; width: 30%;">
                    <div style="font-size: 26px; font-weight: 900; color: #212121;">{bilet['G_Saat']}</div>
                    <div style="font-size: 13px; color: #666; font-weight: 500;">{bilet['Kalkış']} <br> {bilet['G_Tarih']}</div>
                </div>
                
                <div style="color: #bdbdbd; font-size: 28px; text-align: center; width: 20%;">
                    ⟷
                </div>
                
                <div style="text-align: right; width: 30%;">
                    <div style="font-size: 26px; font-weight: 900; color: #212121;">{bilet['D_Saat']}</div>
                    <div style="font-size: 13px; color: #666; font-weight: 500;">{bilet['Varış']} <br> {bilet['D_Tarih']}</div>
                </div>
            </div>
        </div>
        <div style="background: #fafafa; width: 140px; display: flex; flex-direction: column; justify-content: center; align-items: center; border-left: 2px dashed #d0d0d0;">
            <div style="font-size: 12px; color: #777; margin-bottom: 5px;">Toplam Tutar</div>
            <div style="font-size: 24px; font-weight: bold; color: #2e7d32;">{int(bilet['Fiyat'])}</div>
            <div style="font-size: 14px; color: #388e3c; font-weight:600;">{bilet['Para']}</div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# --- 3. ARAYÜZ ---
st.set_page_config(page_title="Jarvis Air v4", layout="centered")

st.title("🛫 Jarvis Uçuş Bulucu")
st.caption("Kişisel seyahat asistanınız, en iyi 5 gidiş-dönüş fırsatını tarıyor...")

with st.sidebar:
    st.header("Seyahat Planı")
    
    kalkis_secim = st.selectbox("Kalkış", list(KALKIS_NOKTALARI.keys()))
    kalkis_code = KALKIS_NOKTALARI[kalkis_secim]
    
    st.markdown("---")
    
    secilen_ulkeler = st.multiselect("Ülke", list(ULKE_SEHIR_VERITABANI.keys()), default=["İtalya"])
    
    olasi_sehirler = {}
    for ulke in secilen_ulkeler:
        olasi_sehirler.update(ULKE_SEHIR_VERITABANI[ulke])
    
    secilen_sehir_isimleri = st.multiselect(
        "Şehirler", 
        options=list(olasi_sehirler.keys()),
        default=list(olasi_sehirler.keys())
    )
    
    hedef_sehir_dict = {k: v for k, v in olasi_sehirler.items() if k in secilen_sehir_isimleri}

    st.markdown("---")
    
    seyahat_suresi = st.slider("Gün Sayısı", 2, 10, 3)
    arama_araligi = st.slider("Tarama Aralığı", 3, 30, 7)
    
    btn_ara = st.button("Uçuşları Bul", type="primary")

# --- 4. AKIŞ ---
if btn_ara:
    if not hedef_sehir_dict:
        st.error("Lütfen şehir seçin Sir.")
    else:
        sonuclar = hizli_arama_motoru(kalkis_code, hedef_sehir_dict, date.today(), arama_araligi, seyahat_suresi)
        
        if sonuclar:
            df = pd.DataFrame(sonuclar).sort_values(by="Fiyat")
            st.success(f"Toplam {len(df)} adet Gidiş-Dönüş uçuşu bulundu. En ucuz 5 seçenek listeleniyor:")
            
            # --- FİNAL DOKUNUŞ: Sadece ilk 5 bileti göster ---
            for i, row in df.head(5).iterrows():
                bilet_kart_ciz(row)
        else:
            st.error("Uçuş bulunamadı.")

import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, timedelta
import concurrent.futures
import textwrap

# --- 1. AYARLAR VE API (GÜVENLİ VE GENİŞLETİLMİŞ) ---
# Not: Prodüksiyon ortamında Key'leri Environment Variable olarak saklamanız önerilir.
amadeus = Client(
    client_id='eN67W0VVx8WfcYKAc4GvzJcy3bapkIUe',
    client_secret='uZxH10uZmCnhGUiS'
)

# Havayolu Kodları (Genişletilmiş)
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
    """
    API Sorgusu - Kapasite Artırıldı (Max 10)
    """
    kalkis, varis, gidis_tarihi, seyahat_suresi = parametreler
    donus_tarihi = gidis_tarihi + timedelta(days=seyahat_suresi)
    
    try:
        # nonStop=False yaparak aktarmalı ucuz uçuşları da veritabanından çekiyoruz.
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=kalkis,
            destinationLocationCode=varis,
            departureDate=gidis_tarihi.strftime("%Y-%m-%d"),
            returnDate=donus_tarihi.strftime("%Y-%m-%d"),
            adults=1,
            max=10  # ÖNEMLİ: Tek seferde 10 alternatif çekiyoruz ki filtreye takılan olursa yedeği olsun.
        )
        return response.data, varis
    except ResponseError as error:
        # Hata logunu konsola basabiliriz ama kullanıcıya boş döneriz
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor: # Worker sayısı optimize edildi
        future_to_search = {executor.submit(tekil_arama_yap, p): p for p in tum_gorevler}
        
        for future in concurrent.futures.as_completed(future_to_search):
            ham_veriler, ilgili_iata = future.result()
            
            sehir_ismi = [k for k, v in hedef_sehirler_dict.items() if v == ilgili_iata][0]
            
            if ham_veriler:
                # Gelen 10 uçuş içinden en uygununu bulup işleyeceğiz
                for ucus in ham_veriler:
                    try:
                        # --- GİDİŞ BACAĞI ANALİZİ ---
                        itinerary_gidis = ucus['itineraries'][0]
                        segmentler_gidis = itinerary_gidis['segments']
                        
                        ilk_nokta = segmentler_gidis[0]['departure']['iataCode']
                        son_nokta = segmentler_gidis[-1]['arrival']['iataCode']
                        
                        # FİLTRE: Eğer kullanıcı IST istedi ama API SAW verdiyse ATLAMA YAP
                        if ilk_nokta != kalkis_kodu:
                            continue

                        # --- DÖNÜŞ BACAĞI ANALİZİ ---
                        itinerary_donus = ucus['itineraries'][1]
                        segmentler_donus = itinerary_donus['segments']
                        
                        # Tarih ve Saatler (İlk segmentin kalkışı, Son segmentin varışı)
                        tarih_g_full = segmentler_gidis[0]['departure']['at']
                        tarih_d_full = segmentler_donus[0]['departure']['at']
                        
                        # --- FİYAT VE DETAYLAR ---
                        fiyat = float(ucus['price']['total'])
                        para = ucus['price']['currency']
                        
                        # Ana taşıyıcı (Genelde ilk segmentin havayolu)
                        h_kod = segmentler_gidis[0]['carrierCode']
                        h_ad = HAVAYOLU_ISIMLERI.get(h_kod, h_kod)
                        
                        # Aktarma Kontrolü
                        toplam_bacak = len(segmentler_gidis) + len(segmentler_donus)
                        tip = "Direkt" if toplam_bacak == 2 else f"{toplam_bacak-2} Aktarma"

                        islenmis_sonuclar.append({
                            "Şehir": sehir_ismi,
                            "Kalkış": ilk_nokta,
                            "Varış": son_nokta, # Artık son segmentin varışını alıyoruz, doğru şehir gelir.
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
                        
                        # Her şehir/tarih için sadece en ucuz 1 tanesini listeye alıp döngüden çıkalım
                        # (Aynı gün için 10 tane alt alta dizmemek için)
                        break 
                        
                    except Exception as e:
                        continue # Bir veri bozuksa diğerine geç
            
            tamamlanan += 1
            bar.progress(tamamlanan / toplam_gorev)
            status.text(f"Veritabanları Taranıyor... %{int((tamamlanan/toplam_gorev)*100)}")
            
    bar.empty()
    status.empty()
    return islenmis_sonuclar

def bilet_kart_ciz(bilet):
    # Renk ve Logo Mantığı
    renk_map = {
        "TK": "#C8102E", # Türk Hava Yolları Kırmızısı
        "VF": "#005EB8", "AJ": "#005EB8", # AJet Mavisi
        "PC": "#F4B323", # Pegasus Sarısı
        "LH": "#FAB415", "BA": "#01295F"
    }
    
    renk = renk_map.get(bilet['Kod'], "#455a64") # Varsayılan Gri
    yazi_rengi = "#333" if bilet['Kod'] in ["PC", "LH"] else "#fff" # Sarı üzerine siyah, diğerlerine beyaz yazı
    
    # Fiyat Formatlama (Binlik ayracı ve tamsayı)
    fiyat_gosterim = f"{int(bilet['Fiyat']):,}".replace(",", ".")
    
    html = textwrap.dedent(f"""
    <div style="font-family: 'Helvetica Neue', sans-serif; background: #fff; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); margin-bottom: 24px; border: 1px solid #eee; overflow: hidden; display: flex; flex-direction: row;">
        
        <div style="background: {renk}; width: 60px; display: flex; align-items: center; justify-content: center; flex-direction: column;">
            <div style="color: {yazi_rengi}; font-weight: 900; font-size: 18px; transform: rotate(-90deg); white-space: nowrap;">{bilet['Kod']}</div>
        </div>
        
        <div style="flex: 1; padding: 20px 24px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 16px;">
                <span style="font-weight: 700; color: #2c3e50; font-size: 18px;">{bilet['Havayolu']}</span>
                <span style="background: #f8f9fa; color: #666; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; border: 1px solid #e0e0e0;">
                    {bilet['Tip']}
                </span>
            </div>
            
            <div style="display: flex; align-items: center; justify-content: space-between;">
                <div style="text-align: left;">
                    <div style="font-size: 28px; font-weight: 800; color: #212529; line-height: 1;">{bilet['G_Saat']}</div>
                    <div style="font-size: 14px; color: #868e96; margin-top: 4px;">{bilet['Kalkış']}</div>
                    <div style="font-size: 12px; color: #adb5bd;">{bilet['G_Tarih']}</div>
                </div>
                
                <div style="flex: 1; text-align: center; padding: 0 20px;">
                    <div style="border-bottom: 2px dashed #dee2e6; position: relative; top: -5px;"></div>
                    <div style="color: #dee2e6; font-size: 20px; margin-top: -16px;">✈</div>
                </div>
                
                <div style="text-align: right;">
                    <div style="font-size: 28px; font-weight: 800; color: #212529; line-height: 1;">{bilet['D_Saat']}</div>
                    <div style="font-size: 14px; color: #868e96; margin-top: 4px;">{bilet['Varış']}</div>
                    <div style="font-size: 12px; color: #adb5bd;">{bilet['D_Tarih']}</div>
                </div>
            </div>
        </div>
        
        <div style="width: 140px; border-left: 2px dashed #e9ecef; display: flex; flex-direction: column; align-items: center; justify-content: center; background: #f8f9fa;">
            <div style="font-size: 12px; color: #868e96; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;">TOPLAM</div>
            <div style="font-size: 26px; font-weight: 900; color: #28a745; margin: 4px 0;">{fiyat_gosterim}</div>
            <div style="font-size: 14px; font-weight: 700; color: #28a745;">{bilet['Para']}</div>
        </div>
    </div>
    """)
    st.markdown(html, unsafe_allow_html=True)

# --- 3. ARAYÜZ ---
st.set_page_config(page_title="Jarvis Air v5.0", layout="centered", page_icon="✈️")

st.markdown("<h1 style='text-align: center; color: #2c3e50;'>✈ Jarvis Flight Manager</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #7f8c8d;'>Tüm veritabanları taranarak en optimize rotalar oluşturuluyor.</p>", unsafe_allow_html=True)

with st.sidebar:
    st.header("📋 Operasyon Parametreleri")
    
    kalkis_secim = st.selectbox("Kalkış Noktası", list(KALKIS_NOKTALARI.keys()))
    kalkis_code = KALKIS_NOKTALARI[kalkis_secim]
    
    st.markdown("---")
    
    secilen_ulkeler = st.multiselect("Hedef Bölge/Ülke", list(ULKE_SEHIR_VERITABANI.keys()), default=["İtalya", "Hollanda"])
    
    olasi_sehirler = {}
    for ulke in secilen_ulkeler:
        olasi_sehirler.update(ULKE_SEHIR_VERITABANI[ulke])
    
    secilen_sehir_isimleri = st.multiselect(
        "Spesifik Şehirler", 
        options=list(olasi_sehirler.keys()),
        default=list(olasi_sehirler.keys())[:3]
    )
    
    hedef_sehir_dict = {k: v for k, v in olasi_sehirler.items() if k in secilen_sehir_isimleri}

    st.markdown("---")
    
    col1, col2 = st.columns(2)
    with col1:
        seyahat_suresi = st.number_input("Kalınacak Gün", min_value=1, value=4)
    with col2:
        arama_araligi = st.number_input("Tarama (Gün)", min_value=1, max_value=60, value=7)
    
    btn_ara = st.button("🔍 UÇUŞLARI GETİR", type="primary", use_container_width=True)

# --- 4. AKIŞ VE SUNUM ---
if btn_ara:
    if not hedef_sehir_dict:
        st.warning("Sir, lütfen en az bir hedef şehir seçiniz.")
    else:
        # Sonuçları al
        sonuclar = hizli_arama_motoru(kalkis_code, hedef_sehir_dict, date.today(), arama_araligi, seyahat_suresi)
        
        if sonuclar:
            df = pd.DataFrame(sonuclar).sort_values(by="Fiyat")
            
            st.success(f"İşlem Tamamlandı: {len(df)} adet uygun rota bulundu.")
            st.markdown("---")
            
            # En ucuz 10 uçuşu göster
            for i, row in df.head(10).iterrows():
                bilet_kart_ciz(row)
        else:
            st.error("Kriterlere uygun uçuş bulunamadı Sir.")
            st.info("💡 İpucu: 'Tarama Aralığı'nı artırmayı veya farklı bir kalkış noktası seçmeyi deneyebilirsiniz. API Sandbox limiti dolmuş olabilir.")

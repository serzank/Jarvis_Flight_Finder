import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, timedelta
import concurrent.futures # Hızlandırma motorumuz (Paralel işlem)

# --- 1. AYARLAR VE API BAĞLANTISI ---
amadeus = Client(
    client_id='eN67W0VVx8WfcYKAc4GvzJcy3bapkIUe',
    client_secret='uZxH10uZmCnhGUiS'
)

# --- 2. VERİTABANI ---
# Kalkış Noktaları Listesi
KALKIS_NOKTALARI = {
    "İstanbul - Avrupa (IST)": "IST",
    "İstanbul - Sabiha Gökçen (SAW)": "SAW",
    "Ankara (ESB)": "ESB",
    "İzmir (ADB)": "ADB",
    "Antalya (AYT)": "AYT",
    "Bodrum (BJV)": "BJV",
    "Dalaman (DLM)": "DLM"
}

# Varış Noktaları (Genişletilmiş)
ULKE_SEHIR_VERITABANI = {
    "İtalya": {"Roma": "FCO", "Milano": "MXP", "Venedik": "VCE", "Napoli": "NAP", "Bolonya": "BLQ"},
    "Hollanda": {"Amsterdam": "AMS", "Rotterdam": "RTM", "Eindhoven": "EIN"},
    "Polonya": {"Varşova": "WAW", "Krakow": "KRK", "Gdansk": "GDN"},
    "Birleşik Krallık": {"Londra (Tümü)": "LON", "Manchester": "MAN"},
    "Danimarka": {"Kopenhag": "CPH", "Billund": "BLL"},
    "Bulgaristan": {"Sofya": "SOF"},
    "Almanya": {"Berlin": "BER", "Münih": "MUC", "Frankfurt": "FRA", "Köln": "CGN"},
    "Fransa": {"Paris": "PAR", "Nice": "NCE"},
    "İspanya": {"Barselona": "BCN", "Madrid": "MAD"},
    "Türkiye İçi": {"İzmir": "ADB", "Antalya": "AYT", "Trabzon": "TZX"}
}

# --- 3. FONKSİYONLAR ---

def tekil_arama_yap(parametreler):
    """
    Paralel işlemci tarafından çağrılacak tekil arama fonksiyonu.
    """
    kalkis, varis, gidis_tarihi, seyahat_suresi = parametreler
    donus_tarihi = gidis_tarihi + timedelta(days=seyahat_suresi)
    
    try:
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=kalkis,
            destinationLocationCode=varis,
            departureDate=gidis_tarihi.strftime("%Y-%m-%d"),
            returnDate=donus_tarihi.strftime("%Y-%m-%d"),
            adults=1,
            max=3 # Her gün için en ucuz 3 uçuş
        )
        return response.data, varis # Veriyi ve hangi şehre ait olduğunu döndür
    except ResponseError:
        return [], varis

@st.cache_data(ttl=600, show_spinner=False) # 10 dakika önbellekleme (Hız için)
def toplu_arama_motoru(kalkis_kodu, hedef_sehirler, baslangic_tarihi, arama_araligi, seyahat_suresi):
    """
    Tüm tarihleri ve şehirleri AYNI ANDA (Paralel) tarayan ana motor.
    """
    tum_gorevler = []
    
    # Tüm kombinasyonları bir görev listesi haline getir
    for sehir_adi, iata_kodu in hedef_sehirler.items():
        for i in range(1, arama_araligi + 1):
            tarih = baslangic_tarihi + timedelta(days=i)
            # Parametre paketini hazırla
            tum_gorevler.append((kalkis_kodu, iata_kodu, tarih, seyahat_suresi))
    
    islenmis_sonuclar = []
    
    # ThreadPoolExecutor ile çoklu işlem başlat (Aynı anda 10 sorgu)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        # Görevleri dağıt
        future_to_search = {executor.submit(tekil_arama_yap, p): p for p in tum_gorevler}
        
        # Tamamlananları topla
        for future in concurrent.futures.as_completed(future_to_search):
            ham_veri, ilgili_iata = future.result()
            
            # Hangi şehir ismi olduğunu bul (Ters arama)
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
            
            gidis_bacaklari = ucus['itineraries'][0]['segments']
            donus_bacaklari = ucus['itineraries'][1]['segments']
            
            gidis_aktarma = len(gidis_bacaklari) - 1
            donus_aktarma = len(donus_bacaklari) - 1
            
            havayolu = gidis_bacaklari[0]['carrierCode']
            
            # Uçuş saatleri
            g_tarih = gidis_bacaklari[0]['departure']['at'].replace('T', ' ')
            d_tarih = donus_bacaklari[0]['departure']['at'].replace('T', ' ')
            
            islenmis_liste.append({
                "Varış Şehri": sehir_adi,
                "Fiyat": fiyat,
                "Para Birimi": para_birimi,
                "Havayolu": havayolu,
                "Aktarma": "Direkt" if (gidis_aktarma + donus_aktarma) == 0 else "Aktarmalı",
                "Gidiş Tarihi": g_tarih,
                "Dönüş Tarihi": d_tarih,
                "Toplam Aktarma": gidis_aktarma + donus_aktarma
            })
        except:
            continue
    return islenmis_liste

# --- 4. ARAYÜZ ---

st.set_page_config(page_title="Jarvis Flight Manager Pro", layout="wide")

st.title("🚀 Jarvis - Hızlı Uçuş Arama Motoru")
st.markdown("---")

with st.sidebar:
    st.header("1. Kalkış Noktası")
    secilen_kalkis_ismi = st.selectbox(
        "Nereden uçuyoruz Sir?",
        options=list(KALKIS_NOKTALARI.keys())
    )
    kalkis_code = KALKIS_NOKTALARI[secilen_kalkis_ismi]
    
    st.header("2. Rota Seçimi")
    secilen_ulkeler = st.multiselect(
        "Hangi ülkelere bakalım?",
        options=list(ULKE_SEHIR_VERITABANI.keys()),
        default=["İtalya"]
    )
    
    hedef_sehir_listesi = {}
    for ulke in secilen_ulkeler:
        hedef_sehir_listesi.update(ULKE_SEHIR_VERITABANI[ulke])
    
    secilen_sehirler_final = st.multiselect(
        "Şehirleri Filtrele",
        options=list(hedef_sehir_listesi.keys()),
        default=list(hedef_sehir_listesi.keys())
    )
    
    # Kodun ihtiyacı olan {Sehir: IATA} sözlüğünü oluştur
    aranacak_sehirler_dict = {k: v for k, v in hedef_sehir_listesi.items() if k in secilen_sehirler_final}

    st.header("3. Zamanlama")
    seyahat_suresi = st.slider("Kaç gün kalacağız?", 2, 10, 4)
    arama_araligi = st.slider("Önümüzdeki kaç gün taransın?", 5, 45, 14) # Aralık artırıldı
    
    sadece_direkt = st.checkbox("Sadece Direkt Uçuşlar", value=False)
    
    st.markdown("---")
    arama_butonu = st.button("Uçuşları Tara (Turbo Mod)", type="primary")

# --- 5. ANA AKIŞ ---

if arama_butonu:
    if not aranacak_sehirler_dict:
        st.error("Lütfen en az bir şehir seçin.")
    else:
        bugun = date.today()
        
        with st.spinner(f"Veritabanı taranıyor... ({len(aranacak_sehirler_dict)} Şehir x {arama_araligi} Gün)"):
            # Önbellekli ve Hızlı Arama Çağrısı
            sonuclar = toplu_arama_motoru(
                kalkis_code, 
                aranacak_sehirler_dict, 
                bugun, 
                arama_araligi, 
                seyahat_suresi
            )
        
        if sonuclar:
            df = pd.DataFrame(sonuclar)
            
            # Filtreleme
            if sadece_direkt:
                df = df[df['Aktarma'] == "Direkt"]
            
            # Sıralama
            df = df.sort_values(by="Fiyat")
            
            st.success(f"İşlem tamamlandı! {len(df)} uçuş bulundu.")
            
            # En iyi fırsatları göster
            en_iyi = df.iloc[0]
            col1, col2, col3 = st.columns(3)
            col1.metric("En İyi Fiyat", f"{en_iyi['Fiyat']:.2f} {en_iyi['Para Birimi']}", en_iyi['Varış Şehri'])
            col2.metric("Tarih", en_iyi['Gidiş Tarihi'][:10])
            col3.metric("Havayolu", en_iyi['Havayolu'])
            
            # Tablo
            st.dataframe(
                df.style.format({"Fiyat": "{:.2f}"}),
                use_container_width=True,
                height=600
            )
        else:
            st.warning("Uçuş bulunamadı.")

import streamlit as st
import pandas as pd
from amadeus import Client, ResponseError
from datetime import date, timedelta

# --- 1. AYARLAR VE API BAĞLANTISI ---
# Buraya Amadeus'tan alacağınız anahtarları gireceksiniz.
amadeus = Client(
    client_id='SIZIN_API_KEY',
    client_secret='SIZIN_API_SECRET'
)

# --- 2. FONKSİYONLAR ---

def ucuslari_ara(kalkis, varis, baslangic_tarihi, seyahat_suresi):
    """
    Belirli bir gidiş tarihi ve seyahat süresine göre uçuş arar.
    Dönüş tarihi = Gidiş Tarihi + Seyahat Süresi
    """
    donus_tarihi = baslangic_tarihi + timedelta(days=seyahat_suresi)
    
    try:
        response = amadeus.shopping.flight_offers_search.get(
            originLocationCode=kalkis,
            destinationLocationCode=varis,
            departureDate=baslangic_tarihi.strftime("%Y-%m-%d"),
            returnDate=donus_tarihi.strftime("%Y-%m-%d"),
            adults=1,
            max=5  # Her tarih için en ucuz 5 uçuşu getir
        )
        return response.data
    except ResponseError as error:
        # Hata olursa (örneğin o tarihte uçuş yoksa) boş dön
        return []

def veriyi_isleme(ham_veri):
    """
    API'den gelen karmaşık JSON verisini temiz bir tabloya çevirir.
    """
    islenmis_liste = []
    for ucus in ham_veri:
        fiyat = ucus['price']['total']
        para_birimi = ucus['price']['currency']
        
        # Gidiş ve Dönüş bacaklarını al
        gidis_bacaklari = ucus['itineraries'][0]['segments']
        donus_bacaklari = ucus['itineraries'][1]['segments']
        
        # Aktarma sayısını hesapla
        gidis_aktarma = len(gidis_bacaklari) - 1
        donus_aktarma = len(donus_bacaklari) - 1
        
        # Havayolu kodu (İlk bacağın taşıyıcısı)
        havayolu = gidis_bacaklari[0]['carrierCode']
        
        islenmis_liste.append({
            "Fiyat": float(fiyat),
            "Para Birimi": para_birimi,
            "Havayolu": havayolu,
            "Gidiş Aktarma": "Direkt" if gidis_aktarma == 0 else f"{gidis_aktarma} Aktarma",
            "Dönüş Aktarma": "Direkt" if donus_aktarma == 0 else f"{donus_aktarma} Aktarma",
            "Gidiş Tarihi": gidis_bacaklari[0]['departure']['at'],
            "Dönüş Tarihi": donus_bacaklari[0]['departure']['at']
        })
    return islenmis_liste

# --- 3. ARAYÜZ (STREAMLIT) ---

st.set_page_config(page_title="Jarvis Flight Finder", layout="wide")

st.title("✈️ Jarvis - Kişisel Uçak Bileti Asistanı")
st.markdown("*Hoş geldiniz Sir. Favori rotalarınız için en iyi fiyatları tarıyorum.*")

# Yan Menü (Sidebar) - Filtreler
with st.sidebar:
    st.header("Seyahat Parametreleri")
    kalkis_code = st.text_input("Kalkış Havalimanı (IATA)", value="IST")
    
    # Favori Şehirleriniz (Çoklu Seçim)
    destinasyonlar = st.multiselect(
        "Favori Rotalarınız",
        ["AMS", "FCO", "WAW", "LON", "CPH", "SOF", "ADB"], # Amsterdam, Roma, Varşova, Londra, Kopenhag, Sofya, İzmir
        default=["AMS", "FCO"]
    )
    
    seyahat_suresi = st.slider("Seyahat Süresi (Gün)", 2, 15, 4)
    arama_araligi = st.slider("Önümüzdeki kaç gün için aransın?", 7, 30, 14)
    
    sadece_direkt = st.checkbox("Sadece Direkt Uçuşlar", value=False)
    
    st.write("---")
    arama_butonu = st.button("Uçuşları Tara Sir")

# --- 4. ANA AKIŞ ---

if arama_butonu:
    tum_sonuclar = []
    progress_bar = st.progress(0)
    
    # Bugünün tarihi
    bugun = date.today()
    
    # Toplam işlem sayısı (İlerleme çubuğu için)
    toplam_islem = len(destinasyonlar) * arama_araligi
    sayac = 0
    
    st.info(f"{kalkis_code} kalkışlı, {seyahat_suresi} günlük seyahatler için veritabanı taranıyor...")

    # Her şehir için döngü
    for sehir in destinasyonlar:
        # Belirtilen gün aralığı için döngü (Esnek Tarih Mantığı)
        for i in range(1, arama_araligi + 1): # Yarından başla
            arama_tarihi = bugun + timedelta(days=i)
            
            # API Sorgusu
            ham_sonuclar = ucuslari_ara(kalkis_code, sehir, arama_tarihi, seyahat_suresi)
            temiz_sonuclar = veriyi_isleme(ham_sonuclar)
            
            # Sonuçları ana listeye ekle
            for sonuc in temiz_sonuclar:
                sonuc['Varış Yeri'] = sehir
                tum_sonuclar.append(sonuc)
            
            # İlerleme çubuğunu güncelle
            sayac += 1
            progress_bar.progress(sayac / toplam_islem)

    # --- 5. SONUÇLARI GÖSTERME ---
    
    if tum_sonuclar:
        df = pd.DataFrame(tum_sonuclar)
        
        # Filtreleme (Direkt Uçuş İsteği Varsa)
        if sadece_direkt:
            df = df[(df['Gidiş Aktarma'] == 'Direkt') & (df['Dönüş Aktarma'] == 'Direkt')]
        
        # Fiyata Göre Sıralama (En ucuz en üstte)
        df = df.sort_values(by="Fiyat", ascending=True)
        
        st.success(f"Toplam {len(df)} uygun uçuş bulundu.")
        
        # En iyi 3 seçeneği kart olarak göster
        col1, col2, col3 = st.columns(3)
        en_iyiler = df.head(3).to_dict('records')
        
        if len(en_iyiler) > 0:
            col1.metric(label=f"En Ucuz: {en_iyiler[0]['Varış Yeri']}", value=f"{en_iyiler[0]['Fiyat']} {en_iyiler[0]['Para Birimi']}", delta="En İyi Fırsat")
            col1.write(f"Tarih: {en_iyiler[0]['Gidiş Tarihi'][:10]}")
        
        # Detaylı Tablo
        st.dataframe(df, use_container_width=True)
        
    else:
        st.warning("Kriterlere uygun uçuş bulunamadı veya API limiti aşıldı.")
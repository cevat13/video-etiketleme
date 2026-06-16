# video-etiketleme

S3'e yüklenen `.mp4` videoları otomatik olarak AWS Rekognition ile analiz eden, sonuçları DynamoDB'ye kaydeden serverless bir uygulama.

## Nasıl çalışır

S3 bucket'ına `.mp4` dosyası yüklendiğinde Lambda tetiklenir. Lambda, Rekognition'a asenkron bir analiz işi gönderir ve iş tamamlanana kadar polling yapar. Tespit edilen etiketler (nesne adı + güven skoru) hem CloudWatch'a loglanır hem de DynamoDB'ye kaydedilir.

## Kullanılan servisler

- AWS S3
- AWS Lambda (Python 3.13)
- AWS Rekognition (Video Label Detection)
- AWS DynamoDB
- AWS CloudWatch
- AWS SAM

## Kurulum

AWS CLI ve SAM CLI kurulu olması gerekiyor.

```bash
sam build
sam deploy --guided --capabilities CAPABILITY_NAMED_IAM
```

Deploy tamamlandığında terminal çıktısında S3 bucket adı ve DynamoDB tablo adı görünür.

## Test

```bash
aws s3 cp video.mp4 s3://<bucket-adı>/video.mp4
```

Analiz sonuçlarını görmek için AWS Console'da DynamoDB tablosuna ya da CloudWatch log grubuna bakılabilir.

## Proje yapısı

```
├── template.yaml       # SAM şablonu (tüm AWS kaynakları)
└── src/
    └── handler.py      # Lambda fonksiyonu
```

## Notlar

- Rekognition video analizi asenkron çalışır, kısa videolarda sonuç ~20-30 saniyede gelir.
- Rekognition eu-central-1 bölgesinde desteklenir, deploy bölgesinin bununla uyumlu olması gerekir.

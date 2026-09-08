from pipeline.country import (
    get_country_code,
    extract_country_entities,
    extract_mentioned_countries,
)


def main():
    samples = [
        # 1. 한국어 - 조사 포함 + 여러 국가
        {
            "country": "South Korea",
            "language_code": "ko",
            "title": "한국과 독일, 프랑스와 기술 협력 확대",
            "body": "한국 정부는 독일과 프랑스, 미국과의 협력을 강화하고 일본과도 협의할 예정이다.",
        },

        # 2. 영어 - 같은 국가 여러 번 등장
        {
            "country": "United States",
            "language_code": "en",
            "title": "China and India discuss new trade agreement",
            "body": "China met with India after talks with South Korea. China also discussed the issue with Japan.",
        },

        # 3. 일본어 - 조사 포함
        {
            "country": "Japan",
            "language_code": "ja",
            "title": "日本と韓国、米国との安全保障協力を強化",
            "body": "日本政府は韓国や米国と協議し、中国との関係についても意見を交換した。",
        },

        # 4. 독일어
        {
            "country": "Germany",
            "language_code": "de",
            "title": "Deutschland und Frankreich beraten über China",
            "body": "Deutschland sprach mit Frankreich und Japan über die Beziehungen zu China und Indien.",
        },

        # 5. 영어 - 영국 표현 확인
        {
            "country": "United Kingdom",
            "language_code": "en",
            "title": "Britain and Germany hold talks with the United States",
            "body": "The United Kingdom met Germany and France before discussions with the United States.",
        },

        # 6. 아랍어 - 접속사 و가 붙는 경우
        {
            "country": "United Kingdom",
            "language_code": "ar",
            "title": "ألمانيا وفرنسا تبحثان العلاقات مع الصين",
            "body": "ألمانيا وفرنسا ناقشتا التعاون مع اليابان والهند والولايات المتحدة.",
        },

        # 7. 프랑스어
        {
            "country": "Germany",
            "language_code": "fr",
            "title": "La France et l'Allemagne discutent avec le Japon",
            "body": "La France a rencontré l'Allemagne, la Chine et l'Inde avant une réunion avec le Japon.",
        },

        # 8. 스페인어
        {
            "country": "United States",
            "language_code": "es",
            "title": "Estados Unidos y Japón dialogan sobre China",
            "body": "Estados Unidos habló con Japón, Alemania e India sobre las relaciones con China.",
        },
    ]

    for article in samples:
        print("=" * 60)

        source_country_code = get_country_code(article["country"])

    # GLiNER 원본 추출 결과
        entities = extract_country_entities(article)

        mentioned_countries = extract_mentioned_countries(
            article,
            article["language_code"],
        )

        print(f"source country: {article['country']}")
        print(f"source country code: {source_country_code}")
        print(f"language: {article['language_code']}")

        print("raw entities:")
        for entity in entities:
            print(entity)

        print(f"mentioned countries: {mentioned_countries}")


if __name__ == "__main__":
    main()
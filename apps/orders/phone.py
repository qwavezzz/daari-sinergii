"""Checkout calling codes and national lengths for the supported countries.

Source: google/libphonenumber resources/PhoneNumberMetadata.xml (2026-10-02).
Only ordinary fixed-line/mobile lengths are used, not short or service numbers.
"""

COUNTRIES = {
    "RU": ("7", 10, "🇷🇺", "Россия"),
    "KZ": ("7", 10, "🇰🇿", "Казахстан"),
    "BY": ("375", 9, "🇧🇾", "Беларусь"),
    "AM": ("374", 8, "🇦🇲", "Армения"),
    "AZ": ("994", 9, "🇦🇿", "Азербайджан"),
    "GE": ("995", 9, "🇬🇪", "Грузия"),
    "KG": ("996", 9, "🇰🇬", "Кыргызстан"),
    "MD": ("373", 8, "🇲🇩", "Молдова"),
    "TJ": ("992", 9, "🇹🇯", "Таджикистан"),
    "TM": ("993", 8, "🇹🇲", "Туркменистан"),
    "UZ": ("998", 9, "🇺🇿", "Узбекистан"),
    "UA": ("380", 9, "🇺🇦", "Украина"),
}

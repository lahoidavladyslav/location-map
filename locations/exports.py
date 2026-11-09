import pandas as pd

COLUMNS = [
    "id", "title", "description", "category__name", "address",
    "latitude", "longitude", "author__username",
    "avg_rating", "reviews_count", "views_7d", "popularity",
    "created_at", "updated_at",
]

RENAME = {"category__name": "category", "author__username": "author"}


def build_dataframe(queryset) -> pd.DataFrame:
    rows = list(queryset.values(*COLUMNS))
    df = pd.DataFrame.from_records(rows, columns=COLUMNS).rename(columns=RENAME)

    df[["latitude", "longitude"]] = df[["latitude", "longitude"]].astype(float)
    df["avg_rating"] = pd.to_numeric(df["avg_rating"]).round(2)
    df["popularity"] = pd.to_numeric(df["popularity"]).round(2)

    for col in ("created_at", "updated_at"):
        df[col] = pd.to_datetime(df[col], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df


def to_json(df: pd.DataFrame) -> str:
    return df.to_json(orient="records", force_ascii=False)


def to_csv(df: pd.DataFrame) -> str:
    # utf-8-sig adds BOM so Excel correctly opens Cyrillic characters
    return df.to_csv(index=False)
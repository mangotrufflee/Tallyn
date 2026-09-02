import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

NUM_TRANSACTIONS = 500

RANDOM_SEED = 42

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)


# ============================================================
# VENDOR MASTER DATA
# ============================================================

vendors = [
    {
        "short": "AWS INDIA",
        "full": "Amazon Web Services India Pvt Ltd",
    },
    {
        "short": "META ADS",
        "full": "Meta Platforms India",
    },
    {
        "short": "FLIPKART",
        "full": "Flipkart Internet Pvt Ltd",
    },
    {
        "short": "GOOGLE CLOUD",
        "full": "Google Cloud India",
    },
    {
        "short": "SWIGGY",
        "full": "Swiggy Pvt Ltd",
    },
    {
        "short": "RAZORPAY",
        "full": "Razorpay Software Pvt Ltd",
    },
    {
        "short": "AMAZON",
        "full": "Amazon Seller Services",
    },
    {
        "short": "UBER",
        "full": "Uber India Systems Pvt Ltd",
    },
    {
        "short": "NETFLIX",
        "full": "Netflix Entertainment Services",
    },
    {
        "short": "ZOHO",
        "full": "Zoho Corporation Pvt Ltd",
    },
]


# ============================================================
# DATE RANGE
# ============================================================

START_DATE = datetime(
    2026,
    1,
    1
)

END_DATE = datetime(
    2026,
    8,
    31
)


def random_date():
    """
    Generate a random transaction date.
    """

    days = (
        END_DATE - START_DATE
    ).days

    random_days = random.randint(
        0,
        days
    )

    return (
        START_DATE
        + timedelta(days=random_days)
    )


def generate_amount():
    """
    Generate a realistic-looking transaction amount.
    """

    amount = random.choice([
        500,
        750,
        1200,
        2500,
        5000,
        6500,
        7200,
        8900,
        9500,
        11000,
        12500,
        15000,
        18000,
        22000,
        35000,
        50000,
        75000,
        100000,
    ])

    return float(amount)


def generate_data():
    """
    Generate synthetic bank, ERP and ground-truth datasets.
    """

    bank_records = []
    erp_records = []
    ground_truth_records = []

    # --------------------------------------------------------
    # Generate the base transactions
    # --------------------------------------------------------

    for i in range(
        1,
        NUM_TRANSACTIONS + 1
    ):

        transaction_id = f"B{i:04d}"

        invoice_id = f"INV{i:04d}"

        vendor = random.choice(
            vendors
        )

        amount = generate_amount()

        date = random_date()

        # ----------------------------------------------------
        # Bank record
        # ----------------------------------------------------

        bank_records.append({
            "transaction_id": transaction_id,
            "date": date.strftime("%Y-%m-%d"),
            "amount": amount,
            "description": vendor["short"],
            "counterparty": vendor["short"],
        })

        # ----------------------------------------------------
        # ERP record
        # ----------------------------------------------------

        erp_records.append({
            "invoice_id": invoice_id,
            "date": date.strftime("%Y-%m-%d"),
            "amount": amount,
            "vendor": vendor["full"],
            "reference": transaction_id,
        })

        # ----------------------------------------------------
        # Ground truth
        # ----------------------------------------------------

        ground_truth_records.append({
            "transaction_id": transaction_id,
            "expected_invoice": invoice_id,
        })

    # ========================================================
    # INTRODUCE DATA QUALITY ISSUES
    # ========================================================

    bank_df = pd.DataFrame(
        bank_records
    )

    erp_df = pd.DataFrame(
        erp_records
    ).copy()

    ground_truth_df = pd.DataFrame(
        ground_truth_records
    )

    # Convert dates
    bank_df["date"] = pd.to_datetime(
        bank_df["date"]
    )

    erp_df["date"] = pd.to_datetime(
        erp_df["date"]
    )

    # --------------------------------------------------------
    # 1. DATE VARIATIONS
    # --------------------------------------------------------

    date_indices = random.sample(
        range(NUM_TRANSACTIONS),
        int(NUM_TRANSACTIONS * 0.10)
    )

    for index in date_indices:

        erp_df.loc[
            index,
            "date"
        ] += timedelta(
            days=random.choice(
                [1, 2]
            )
        )

    # --------------------------------------------------------
    # 2. SMALL AMOUNT DIFFERENCES
    # --------------------------------------------------------

    amount_indices = random.sample(
        range(NUM_TRANSACTIONS),
        int(NUM_TRANSACTIONS * 0.06)
    )

    for index in amount_indices:

        erp_df.loc[
            index,
            "amount"
        ] = erp_df.loc[
            index,
            "amount"
        ] + random.choice(
            [50, 100, 200, 500]
        )

    # --------------------------------------------------------
    # 3. LARGE AMOUNT DIFFERENCES
    # --------------------------------------------------------

    large_amount_indices = random.sample(
        range(NUM_TRANSACTIONS),
        int(NUM_TRANSACTIONS * 0.04)
    )

    for index in large_amount_indices:

        erp_df.loc[
            index,
            "amount"
        ] = erp_df.loc[
            index,
            "amount"
        ] + random.choice(
            [1000, 2000, 5000]
        )

    # --------------------------------------------------------
    # 4. MISSING ERP RECORDS
    # --------------------------------------------------------

    missing_erp_indices = random.sample(
        range(NUM_TRANSACTIONS),
        int(NUM_TRANSACTIONS * 0.05)
    )

    missing_invoice_ids = set()

    for index in missing_erp_indices:

        missing_invoice_ids.add(
            erp_df.loc[
                index,
                "invoice_id"
            ]
        )

    erp_df = erp_df[
        ~erp_df["invoice_id"].isin(
            missing_invoice_ids
        )
    ].copy()

    # --------------------------------------------------------
    # 5. DUPLICATE ERP RECORDS
    # --------------------------------------------------------

    duplicate_indices = random.sample(
        range(len(erp_df)),
        int(NUM_TRANSACTIONS * 0.03)
    )

    duplicate_rows = erp_df.iloc[
        duplicate_indices
    ].copy()

    duplicate_rows[
        "invoice_id"
    ] = duplicate_rows[
        "invoice_id"
    ] + "_DUP"

    erp_df = pd.concat(
        [
            erp_df,
            duplicate_rows
        ],
        ignore_index=True
    )

    # --------------------------------------------------------
    # 6. SHUFFLE EVERYTHING
    # --------------------------------------------------------

    bank_df = bank_df.sample(
        frac=1,
        random_state=RANDOM_SEED
    ).reset_index(
        drop=True
    )

    erp_df = erp_df.sample(
        frac=1,
        random_state=RANDOM_SEED
    ).reset_index(
        drop=True
    )

    # ========================================================
    # SAVE FILES
    # ========================================================

    bank_df.to_csv(
        "data/bank.csv",
        index=False
    )

    erp_df.to_csv(
        "data/erp.csv",
        index=False
    )

    ground_truth_df.to_csv(
        "data/verification.csv",
        index=False
    )

    # ========================================================
    # PRINT SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print("SYNTHETIC DATA GENERATED")
    print("=" * 70)

    print(
        f"Bank records: {len(bank_df)}"
    )

    print(
        f"ERP records: {len(erp_df)}"
    )

    print(
        f"Ground truth records: "
        f"{len(ground_truth_df)}"
    )

    print(
        f"Missing ERP records: "
        f"{len(missing_erp_indices)}"
    )

    print(
        f"Duplicate ERP records: "
        f"{len(duplicate_rows)}"
    )

    print("=" * 70)


if __name__ == "__main__":
    generate_data()
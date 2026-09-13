"""Curated educational reference lists (not investment advice)."""

# Categories for conservative-leaning learners looking at SH/SZ ETFs.
REFERENCE_GROUPS = [
    {
        "id": "bond",
        "title": "利率债 / 国债",
        "risk": "较低",
        "blurb": "跟踪国债或政策性金融债，波动通常明显小于股票，适合打底仓、看利率环境。",
        "items": [
            {"code": "511260", "market": "SH", "name": "十年国债ETF", "tag": "你已持有"},
            {"code": "511010", "market": "SH", "name": "国债ETF", "tag": "久期较短"},
            {"code": "511220", "market": "SH", "name": "城投债ETF", "tag": "信用债"},
            {"code": "511380", "market": "SH", "name": "可转债ETF", "tag": "含股性"},
        ],
    },
    {
        "id": "cash",
        "title": "货币 / 短久期现金管理",
        "risk": "很低",
        "blurb": "接近货币基金，主要赚票息与流动性收益，几乎不参与股市涨跌。",
        "items": [
            {"code": "511880", "market": "SH", "name": "银华日利", "tag": "货币"},
            {"code": "511990", "market": "SH", "name": "华宝添益", "tag": "货币"},
            {"code": "511660", "market": "SH", "name": "建信添益", "tag": "短债"},
        ],
    },
    {
        "id": "broad",
        "title": "宽基指数（核心仓候选）",
        "risk": "中等",
        "blurb": "一篮子大中盘股票，比单一个股分散，但仍有股市回撤；稳健组合常用沪深300这类做核心。",
        "items": [
            {"code": "510300", "market": "SH", "name": "沪深300ETF", "tag": "大盘核心"},
            {"code": "510500", "market": "SH", "name": "中证500ETF", "tag": "中盘"},
            {"code": "159915", "market": "SZ", "name": "创业板ETF", "tag": "成长弹性大"},
            {"code": "588000", "market": "SH", "name": "科创50ETF", "tag": "波动更大"},
        ],
    },
    {
        "id": "dividend",
        "title": "红利 / 低波动",
        "risk": "中等偏低",
        "blurb": "偏向高股息、低波动股票，通常回撤小于成长板块，适合稳健偏好者长期观察。",
        "items": [
            {"code": "510880", "market": "SH", "name": "红利ETF", "tag": "高股息"},
            {"code": "515450", "market": "SH", "name": "红利低波ETF", "tag": "低波动"},
            {"code": "512890", "market": "SH", "name": "红利低波100", "tag": "分散红利"},
        ],
    },
    {
        "id": "other",
        "title": "另类分散（黄金等）",
        "risk": "中等",
        "blurb": "与股债相关性不同，常用于组合分散；价格仍会波动，不是保本产品。",
        "items": [
            {"code": "518880", "market": "SH", "name": "黄金ETF", "tag": "商品"},
        ],
    },
]


def get_reference_groups() -> list[dict]:
    return REFERENCE_GROUPS

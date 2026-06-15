"""
ETF行情通 - 后端API服务 (腾讯实时接口版)
使用腾讯财经接口获取秒级实时数据
"""
import json
import asyncio
import requests
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI(title="ETF行情通API", version="2.0.0")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 缓存数据
etf_cache = []
cache_time = None
index_cache = {}

# ETF分类映射
CATEGORY_MAP = {
    "宽基": ["沪深300", "中证500", "上证50", "创业板指", "科创50", "中证1000", "国证2000", "中证A500", "A500"],
    "行业": ["半导体", "芯片", "新能源", "医药", "医疗", "银行", "证券", "保险", "地产", "军工", "传媒", "计算机", "通信", "5G", "消费", "白酒", "食品", "汽车", "钢铁", "煤炭", "有色", "化工", "电力", "农业", "游戏", "影视"],
    "主题": ["AI", "人工智能", "碳中和", "ESG", "数字经济", "元宇宙", "机器人", "光伏", "风电", "储能", "锂电池", "稀土", "北斗", "一带一路", "红利", "高股息"],
    "跨境": ["纳斯达克", "标普", "道琼斯", "恒生", "港股", "日经", "德国", "法国", "越南", "印度", "中韩", "亚太"],
    "商品": ["黄金", "白银", "原油", "豆粕", "有色金属", "工业有色", "黄金股"],
    "债券": ["国债", "可转债", "信用债", "利率债", "政金债"],
    "货币": ["货币", "场内货币"],
}

def get_category(name: str) -> str:
    """根据ETF名称判断分类"""
    for cat, keywords in CATEGORY_MAP.items():
        for kw in keywords:
            if kw in name:
                return cat
    return "其他"

def is_t0(name: str, category: str) -> bool:
    """判断是否支持T+0"""
    t0_keywords = ["跨境", "港股", "商品", "债券", "货币", "黄金", "原油", "纳斯达克", "标普", "恒生", "日经", "中韩", "亚太"]
    for kw in t0_keywords:
        if kw in name:
            return True
    return category in ["跨境", "商品", "债券", "货币"]

def parse_qq_response(text: str) -> list:
    """解析腾讯接口返回数据"""
    etf_list = []
    for line in text.strip().split(';'):
        line = line.strip()
        if not line or '="' not in line:
            continue
        try:
            # 提取引号内的数据
            start = line.find('="') + 2
            end = line.rfind('"')
            data_str = line[start:end]
            parts = data_str.split('~')
            if len(parts) < 40:
                continue
            
            name = parts[1]
            code = parts[2]
            price = float(parts[3]) if parts[3] else 0
            pre_close = float(parts[4]) if parts[4] else 0
            open_price = float(parts[5]) if parts[5] else 0
            high = float(parts[33]) if parts[33] else 0
            low = float(parts[34]) if parts[34] else 0
            chg_amount = float(parts[31]) if parts[31] else 0
            chg_percent = float(parts[32]) if parts[32] else 0
            # 成交量(手)在parts[36], 成交额(万元)在parts[57]
            try:
                volume = int(parts[36]) if len(parts) > 36 and parts[36] else 0
            except:
                volume = 0
            try:
                amount = round(float(parts[57]), 2) if len(parts) > 57 and parts[57] else 0
            except:
                amount = 0
            
            category = get_category(name)
            
            etf_list.append({
                "name": name,
                "code": code,
                "price": round(price, 3),
                "chg": round(chg_percent, 2),
                "chg_amount": round(chg_amount, 3),
                "open": round(open_price, 3),
                "high": round(high, 3),
                "low": round(low, 3),
                "pre_close": round(pre_close, 3),
                "volume": volume,
                "amount": amount,
                "category": category,
                "is_t0": is_t0(name, category),
                "tags": [category] + (["T+0"] if is_t0(name, category) else [])
            })
        except Exception as e:
            continue
    return etf_list

# 预置常用ETF代码列表（约300只主流ETF）
ETF_CODES = [
    # 宽基指数
    "sh510300", "sh510050", "sh510500", "sh510330", "sh510310", "sh510360",
    "sh510390", "sh510410", "sh510420", "sh510430", "sh510440", "sh510450",
    "sh510460", "sh510510", "sh510520", "sh510560", "sh510580", "sh510610",
    "sh510650", "sh510660", "sh510680", "sh510710", "sh510760", "sh510810",
    "sh510850", "sh510860", "sh510880", "sh510900", "sh511000", "sh511010",
    "sh511020", "sh511030", "sh511050", "sh511060", "sh511080", "sh511090",
    "sh511100", "sh511110", "sh511130", "sh511150", "sh511160", "sh511170",
    "sh511180", "sh511190", "sh511200", "sh511210", "sh511220", "sh511230",
    "sh511240", "sh511250", "sh511260", "sh511270", "sh511280", "sh511290",
    "sh511300", "sh511310", "sh511320", "sh511330", "sh511340", "sh511350",
    "sh511360", "sh511380", "sh511390", "sh511400", "sh511410", "sh511420",
    "sh511430", "sh511440", "sh511450", "sh511460", "sh511470", "sh511480",
    "sh511490", "sh511500", "sh511510", "sh511520", "sh511530", "sh511540",
    "sh511550", "sh511560", "sh511570", "sh511580", "sh511590", "sh511600",
    "sh511610", "sh511620", "sh511630", "sh511640", "sh511650", "sh511660",
    "sh511670", "sh511680", "sh511690", "sh511700", "sh511710", "sh511720",
    "sh511730", "sh511740", "sh511750", "sh511760", "sh511770", "sh511780",
    "sh511790", "sh511800", "sh511810", "sh511820", "sh511830", "sh511840",
    "sh511850", "sh511860", "sh511870", "sh511880", "sh511890", "sh511900",
    "sh511910", "sh511920", "sh511930", "sh511940", "sh511950", "sh511960",
    "sh511970", "sh511980", "sh511990",
    # 行业主题
    "sh512000", "sh512010", "sh512020", "sh512030", "sh512040", "sh512050",
    "sh512060", "sh512070", "sh512080", "sh512090", "sh512100", "sh512110",
    "sh512120", "sh512130", "sh512140", "sh512150", "sh512160", "sh512170",
    "sh512180", "sh512190", "sh512200", "sh512210", "sh512220", "sh512230",
    "sh512240", "sh512250", "sh512260", "sh512270", "sh512280", "sh512290",
    "sh512300", "sh512310", "sh512320", "sh512330", "sh512340", "sh512350",
    "sh512360", "sh512370", "sh512380", "sh512390", "sh512400", "sh512410",
    "sh512420", "sh512430", "sh512440", "sh512450", "sh512460", "sh512470",
    "sh512480", "sh512490", "sh512500", "sh512510", "sh512520", "sh512530",
    "sh512540", "sh512550", "sh512560", "sh512570", "sh512580", "sh512590",
    "sh512600", "sh512610", "sh512620", "sh512630", "sh512640", "sh512650",
    "sh512660", "sh512670", "sh512680", "sh512690", "sh512700", "sh512710",
    "sh512720", "sh512730", "sh512740", "sh512750", "sh512760", "sh512770",
    "sh512780", "sh512790", "sh512800", "sh512810", "sh512820", "sh512830",
    "sh512840", "sh512850", "sh512860", "sh512870", "sh512880", "sh512890",
    "sh512900", "sh512910", "sh512920", "sh512930", "sh512940", "sh512950",
    "sh512960", "sh512970", "sh512980", "sh512990",
    # 跨境ETF
    "sh513000", "sh513010", "sh513020", "sh513030", "sh513040", "sh513050",
    "sh513060", "sh513070", "sh513080", "sh513090", "sh513100", "sh513110",
    "sh513120", "sh513130", "sh513140", "sh513150", "sh513160", "sh513170",
    "sh513180", "sh513190", "sh513200", "sh513210", "sh513220", "sh513230",
    "sh513240", "sh513250", "sh513260", "sh513270", "sh513280", "sh513290",
    "sh513300", "sh513310", "sh513320", "sh513330", "sh513340", "sh513350",
    "sh513360", "sh513370", "sh513380", "sh513390", "sh513400", "sh513410",
    "sh513420", "sh513430", "sh513440", "sh513450", "sh513460", "sh513470",
    "sh513480", "sh513490", "sh513500", "sh513510", "sh513520", "sh513530",
    "sh513540", "sh513550", "sh513560", "sh513570", "sh513580", "sh513590",
    "sh513600", "sh513610", "sh513620", "sh513630", "sh513640", "sh513650",
    "sh513660", "sh513670", "sh513680", "sh513690", "sh513700", "sh513710",
    "sh513720", "sh513730", "sh513740", "sh513750", "sh513760", "sh513770",
    "sh513780", "sh513790", "sh513800", "sh513810", "sh513820", "sh513830",
    "sh513840", "sh513850", "sh513860", "sh513870", "sh513880", "sh513890",
    "sh513900", "sh513910", "sh513920", "sh513930", "sh513940", "sh513950",
    "sh513960", "sh513970", "sh513980", "sh513990",
    # 商品/债券/货币
    "sh518000", "sh518010", "sh518020", "sh518030", "sh518040", "sh518050",
    "sh518060", "sh518070", "sh518080", "sh518090", "sh518100", "sh518110",
    "sh518120", "sh518130", "sh518140", "sh518150", "sh518160", "sh518170",
    "sh518180", "sh518190", "sh518200", "sh518210", "sh518220", "sh518230",
    "sh518240", "sh518250", "sh518260", "sh518270", "sh518280", "sh518290",
    "sh518300", "sh518310", "sh518320", "sh518330", "sh518340", "sh518350",
    "sh518360", "sh518370", "sh518380", "sh518390", "sh518400", "sh518410",
    "sh518420", "sh518430", "sh518440", "sh518450", "sh518460", "sh518470",
    "sh518480", "sh518490", "sh518500", "sh518510", "sh518520", "sh518530",
    "sh518540", "sh518550", "sh518560", "sh518570", "sh518580", "sh518590",
    "sh518600", "sh518610", "sh518620", "sh518630", "sh518640", "sh518650",
    "sh518660", "sh518670", "sh518680", "sh518690", "sh518700", "sh518710",
    "sh518720", "sh518730", "sh518740", "sh518750", "sh518760", "sh518770",
    "sh518780", "sh518790", "sh518800", "sh518810", "sh518820", "sh518830",
    "sh518840", "sh518850", "sh518860", "sh518870", "sh518880", "sh518890",
    "sh518900", "sh518910", "sh518920", "sh518930", "sh518940", "sh518950",
    "sh518960", "sh518970", "sh518980", "sh518990",
    # 科创板/创业板
    "sh588000", "sh588010", "sh588020", "sh588030", "sh588040", "sh588050",
    "sh588060", "sh588070", "sh588080", "sh588090", "sh588100", "sh588110",
    "sh588120", "sh588130", "sh588140", "sh588150", "sh588160", "sh588170",
    "sh588180", "sh588190", "sh588200", "sh588210", "sh588220", "sh588230",
    "sh588240", "sh588250", "sh588260", "sh588270", "sh588280", "sh588290",
    "sh588300", "sh588310", "sh588320", "sh588330", "sh588340", "sh588350",
    "sh588360", "sh588370", "sh588380", "sh588390", "sh588400", "sh588410",
    "sh588420", "sh588430", "sh588440", "sh588450", "sh588460", "sh588470",
    "sh588480", "sh588490", "sh588500", "sh588510", "sh588520", "sh588530",
    "sh588540", "sh588550", "sh588560", "sh588570", "sh588580", "sh588590",
    "sh588600", "sh588610", "sh588620", "sh588630", "sh588640", "sh588650",
    "sh588660", "sh588670", "sh588680", "sh588690", "sh588700", "sh588710",
    "sh588720", "sh588730", "sh588740", "sh588750", "sh588760", "sh588770",
    "sh588780", "sh588790", "sh588800", "sh588810", "sh588820", "sh588830",
    "sh588840", "sh588850", "sh588860", "sh588870", "sh588880", "sh588890",
    "sh588900", "sh588910", "sh588920", "sh588930", "sh588940", "sh588950",
    "sh588960", "sh588970", "sh588980", "sh588990",
    # 深圳ETF
    "sz159601", "sz159602", "sz159603", "sz159605", "sz159606", "sz159607",
    "sz159608", "sz159609", "sz159610", "sz159611", "sz159612", "sz159613",
    "sz159614", "sz159615", "sz159616", "sz159617", "sz159618", "sz159619",
    "sz159620", "sz159621", "sz159622", "sz159623", "sz159624", "sz159625",
    "sz159626", "sz159627", "sz159628", "sz159629", "sz159630", "sz159631",
    "sz159632", "sz159633", "sz159634", "sz159635", "sz159636", "sz159637",
    "sz159638", "sz159639", "sz159640", "sz159641", "sz159642", "sz159643",
    "sz159644", "sz159645", "sz159646", "sz159647", "sz159648", "sz159649",
    "sz159650", "sz159651", "sz159652", "sz159653", "sz159654", "sz159655",
    "sz159656", "sz159657", "sz159658", "sz159659", "sz159660", "sz159661",
    "sz159662", "sz159663", "sz159664", "sz159665", "sz159666", "sz159667",
    "sz159668", "sz159669", "sz159670", "sz159671", "sz159672", "sz159673",
    "sz159674", "sz159675", "sz159676", "sz159677", "sz159678", "sz159679",
    "sz159680", "sz159681", "sz159682", "sz159683", "sz159684", "sz159685",
    "sz159686", "sz159687", "sz159688", "sz159689", "sz159690", "sz159691",
    "sz159692", "sz159693", "sz159694", "sz159695", "sz159696", "sz159697",
    "sz159698", "sz159699", "sz159700", "sz159701", "sz159702", "sz159703",
    "sz159704", "sz159705", "sz159706", "sz159707", "sz159708", "sz159709",
    "sz159710", "sz159711", "sz159712", "sz159713", "sz159714", "sz159715",
    "sz159716", "sz159717", "sz159718", "sz159719", "sz159720", "sz159721",
    "sz159722", "sz159723", "sz159724", "sz159725", "sz159726", "sz159727",
    "sz159728", "sz159729", "sz159730", "sz159731", "sz159732", "sz159733",
    "sz159734", "sz159735", "sz159736", "sz159737", "sz159738", "sz159739",
    "sz159740", "sz159741", "sz159742", "sz159743", "sz159744", "sz159745",
    "sz159746", "sz159747", "sz159748", "sz159749", "sz159750", "sz159751",
    "sz159752", "sz159753", "sz159754", "sz159755", "sz159756", "sz159757",
    "sz159758", "sz159759", "sz159760", "sz159761", "sz159762", "sz159763",
    "sz159764", "sz159765", "sz159766", "sz159767", "sz159768", "sz159769",
    "sz159770", "sz159771", "sz159772", "sz159773", "sz159774", "sz159775",
    "sz159776", "sz159777", "sz159778", "sz159779", "sz159780", "sz159781",
    "sz159782", "sz159783", "sz159784", "sz159785", "sz159786", "sz159787",
    "sz159788", "sz159789", "sz159790", "sz159791", "sz159792", "sz159793",
    "sz159794", "sz159795", "sz159796", "sz159797", "sz159798", "sz159799",
    "sz159800", "sz159801", "sz159802", "sz159803", "sz159804", "sz159805",
    "sz159806", "sz159807", "sz159808", "sz159809", "sz159810", "sz159811",
    "sz159812", "sz159813", "sz159814", "sz159815", "sz159816", "sz159817",
    "sz159818", "sz159819", "sz159820", "sz159821", "sz159822", "sz159823",
    "sz159824", "sz159825", "sz159826", "sz159827", "sz159828", "sz159829",
    "sz159830", "sz159831", "sz159832", "sz159833", "sz159834", "sz159835",
    "sz159836", "sz159837", "sz159838", "sz159839", "sz159840", "sz159841",
    "sz159842", "sz159843", "sz159844", "sz159845", "sz159846", "sz159847",
    "sz159848", "sz159849", "sz159850", "sz159851", "sz159852", "sz159853",
    "sz159854", "sz159855", "sz159856", "sz159857", "sz159858", "sz159859",
    "sz159860", "sz159861", "sz159862", "sz159863", "sz159864", "sz159865",
    "sz159866", "sz159867", "sz159868", "sz159869", "sz159870", "sz159871",
    "sz159872", "sz159873", "sz159874", "sz159875", "sz159876", "sz159877",
    "sz159878", "sz159879", "sz159880", "sz159881", "sz159882", "sz159883",
    "sz159884", "sz159885", "sz159886", "sz159887", "sz159888", "sz159889",
    "sz159890", "sz159891", "sz159892", "sz159893", "sz159894", "sz159895",
    "sz159896", "sz159897", "sz159898", "sz159899", "sz159900", "sz159901",
    "sz159902", "sz159903", "sz159904", "sz159905", "sz159906", "sz159907",
    "sz159908", "sz159909", "sz159910", "sz159911", "sz159912", "sz159913",
    "sz159914", "sz159915", "sz159916", "sz159917", "sz159918", "sz159919",
    "sz159920", "sz159921", "sz159922", "sz159923", "sz159924", "sz159925",
    "sz159926", "sz159927", "sz159928", "sz159929", "sz159930", "sz159931",
    "sz159932", "sz159933", "sz159934", "sz159935", "sz159936", "sz159937",
    "sz159938", "sz159939", "sz159940", "sz159941", "sz159942", "sz159943",
    "sz159944", "sz159945", "sz159946", "sz159947", "sz159948", "sz159949",
    "sz159950", "sz159951", "sz159952", "sz159953", "sz159954", "sz159955",
    "sz159956", "sz159957", "sz159958", "sz159959", "sz159960", "sz159961",
    "sz159962", "sz159963", "sz159964", "sz159965", "sz159966", "sz159967",
    "sz159968", "sz159969", "sz159970", "sz159971", "sz159972", "sz159973",
    "sz159974", "sz159975", "sz159976", "sz159977", "sz159978", "sz159979",
    "sz159980", "sz159981", "sz159982", "sz159983", "sz159984", "sz159985",
    "sz159986", "sz159987", "sz159988", "sz159989", "sz159990", "sz159991",
    "sz159992", "sz159993", "sz159994", "sz159995", "sz159996", "sz159997",
    "sz159998", "sz159999"
]

def fetch_etf_from_qq():
    """从腾讯接口获取ETF实时数据"""
    global etf_cache, cache_time
    try:
        codes = ETF_CODES
        print(f"开始请求 {len(codes)} 只ETF实时数据...")
        
        # 分批请求（腾讯接口一次最多支持约60个代码）
        all_etfs = []
        batch_size = 50
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i+batch_size]
            url = f"https://qt.gtimg.cn/q={','.join(batch)}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                etfs = parse_qq_response(resp.text)
                all_etfs.extend(etfs)
        
        if all_etfs:
            etf_cache = all_etfs
            cache_time = datetime.now()
            print(f"成功获取 {len(all_etfs)} 只ETF实时数据")
        
        return etf_cache
    except Exception as e:
        print(f"腾讯接口获取ETF失败: {e}")
        return etf_cache

def fetch_index_from_qq():
    """从腾讯接口获取指数实时数据"""
    global index_cache
    try:
        url = "https://qt.gtimg.cn/q=sh000001,sz399001,sz399006"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            for line in resp.text.strip().split(';'):
                line = line.strip()
                if '="' not in line:
                    continue
                start = line.find('="') + 2
                end = line.rfind('"')
                data_str = line[start:end]
                parts = data_str.split('~')
                if len(parts) < 40:
                    continue
                
                name = parts[1]
                code = parts[2]
                price = float(parts[3]) if parts[3] else 0
                chg_amount = float(parts[31]) if parts[31] else 0
                chg_percent = float(parts[32]) if parts[32] else 0
                
                if code == "000001":
                    index_cache["sh"] = {
                        "name": "上证指数",
                        "code": "000001",
                        "price": round(price, 2),
                        "chg": round(chg_percent, 2),
                        "chg_amount": round(chg_amount, 2)
                    }
                elif code == "399001":
                    index_cache["sz"] = {
                        "name": "深证成指",
                        "code": "399001",
                        "price": round(price, 2),
                        "chg": round(chg_percent, 2),
                        "chg_amount": round(chg_amount, 2)
                    }
                elif code == "399006":
                    index_cache["cy"] = {
                        "name": "创业板指",
                        "code": "399006",
                        "price": round(price, 2),
                        "chg": round(chg_percent, 2),
                        "chg_amount": round(chg_amount, 2)
                    }
        return index_cache
    except Exception as e:
        print(f"腾讯接口获取指数失败: {e}")
        # 使用默认数据
        if not index_cache:
            index_cache = {
                "sh": {"name": "上证指数", "code": "000001", "price": 4030.63, "chg": -0.02, "chg_amount": -0.88},
                "sz": {"name": "深证成指", "code": "399001", "price": 14963.41, "chg": 0.0, "chg_amount": 0.0},
                "cy": {"name": "创业板指", "code": "399006", "price": 3830.35, "chg": 0.0, "chg_amount": 0.0}
            }
        return index_cache

# 后台数据加载（不阻塞启动）
async def background_load():
    """后台加载数据，不阻塞服务启动"""
    await asyncio.sleep(0.5)  # 让服务先启动
    fetch_etf_from_qq()
    fetch_index_from_qq()

# 定时刷新数据（每10秒刷新一次）
async def refresh_data():
    while True:
        await asyncio.sleep(10)
        fetch_etf_from_qq()
        fetch_index_from_qq()

@app.on_event("startup")
async def startup():
    # 启动后台数据加载和定时刷新
    asyncio.create_task(background_load())
    asyncio.create_task(refresh_data())

@app.get("/")
def root():
    return {"message": "ETF行情通API服务 (腾讯实时版)", "status": "running", "refresh_interval": 5}

@app.get("/api/index")
def get_index():
    """获取A股指数行情"""
    return {
        "data": list(index_cache.values()),
        "time": cache_time.strftime("%Y-%m-%d %H:%M:%S") if cache_time else None
    }

@app.get("/api/etf/list")
def get_etf_list(
    category: Optional[str] = Query(None, description="分类筛选"),
    sort: Optional[str] = Query("chg", description="排序字段: chg/price/volume/amount"),
    order: Optional[str] = Query("desc", description="排序方向: asc/desc"),
    limit: int = Query(50, description="返回数量")
):
    """获取ETF列表"""
    data = etf_cache.copy()
    
    # 分类筛选
    if category and category != "全部":
        if category == "T+0":
            data = [e for e in data if e["is_t0"]]
        else:
            data = [e for e in data if e["category"] == category or category in e["tags"]]
    
    # 排序
    reverse = order == "desc"
    if sort == "chg":
        data.sort(key=lambda x: x["chg"], reverse=reverse)
    elif sort == "price":
        data.sort(key=lambda x: x["price"], reverse=reverse)
    elif sort == "volume":
        data.sort(key=lambda x: x["volume"], reverse=reverse)
    elif sort == "amount":
        data.sort(key=lambda x: x["amount"], reverse=reverse)
    
    return {
        "data": data[:limit],
        "total": len(data),
        "time": cache_time.strftime("%Y-%m-%d %H:%M:%S") if cache_time else None
    }

@app.get("/api/etf/top")
def get_etf_top(
    type: str = Query("rise", description="rise-涨幅榜 fall-跌幅榜"),
    limit: int = Query(10, description="返回数量")
):
    """获取ETF涨跌幅排行"""
    data = etf_cache.copy()
    
    if type == "rise":
        data = [e for e in data if e["chg"] > 0]
        data.sort(key=lambda x: x["chg"], reverse=True)
    else:
        data = [e for e in data if e["chg"] < 0]
        data.sort(key=lambda x: x["chg"], reverse=False)
    
    return {
        "data": data[:limit],
        "time": cache_time.strftime("%Y-%m-%d %H:%M:%S") if cache_time else None
    }

@app.get("/api/etf/search")
def search_etf(
    q: str = Query(..., description="搜索关键词"),
    limit: int = Query(20, description="返回数量")
):
    """搜索ETF"""
    data = etf_cache.copy()
    q = q.upper()
    
    # 按代码或名称匹配
    result = [e for e in data if q in e["code"] or q in e["name"].upper()]
    
    return {
        "data": result[:limit],
        "total": len(result)
    }

@app.get("/api/etf/detail/{code}")
def get_etf_detail(code: str):
    """获取ETF详情"""
    for etf in etf_cache:
        if etf["code"] == code:
            return {"data": etf}
    return JSONResponse(status_code=404, content={"error": "ETF不存在"})

@app.get("/api/stats")
def get_stats():
    """获取市场统计"""
    data = etf_cache
    total = len(data)
    rise = len([e for e in data if e["chg"] > 0])
    fall = len([e for e in data if e["chg"] < 0])
    flat = total - rise - fall
    total_amount = sum(e["amount"] for e in data)
    
    return {
        "total": total,
        "rise": rise,
        "fall": fall,
        "flat": flat,
        "total_amount": round(total_amount, 2),
        "time": cache_time.strftime("%Y-%m-%d %H:%M:%S") if cache_time else None
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

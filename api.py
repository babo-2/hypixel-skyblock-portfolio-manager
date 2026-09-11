import requests, os, json, struct, math, time, statistics, re
from datetime import datetime, timezone

# int64 timestamp + int32 MaxSell + int32 MinBuy
BZ_FORMAT = "<qii"
BZ_ENTRY_SIZE = struct.calcsize(BZ_FORMAT)  # 16 bytes

#int64 timestamp + int32 price
AH_FORMAT = "<qqi"
AH_ENTRY_SIZE = struct.calcsize(AH_FORMAT)  # 16 bytes

#helper
def to_bytes(data: dict) -> bytes:
    """
    Convert:
        {
            timestamp: {
                "MaxSell": maxsell,
                "MinBuy": minbuy
            },
            ...
        }

    into consecutive 16-byte binary entries.
    """
    return b"".join(
        struct.pack(
            BZ_FORMAT,
            int(timestamp),
            int(values["MaxSell"]),
            int(values["MinBuy"]),
        )
        for timestamp, values in data.items()
    )
def from_bytes(data: bytes) -> dict:
    """
    Convert consecutive 16-byte binary entries back into:
        {
            timestamp: {
                "MaxSell": maxsell,
                "MinBuy": minbuy
            },
            ...
        }
    """
    if len(data) % BZ_ENTRY_SIZE != 0:
        raise ValueError(
            f"Invalid data length: {len(data)} bytes "
            f"(must be a multiple of {BZ_ENTRY_SIZE})"
        )

    result = {}

    for offset in range(0, len(data), BZ_ENTRY_SIZE):
        timestamp, max_sell, min_buy = struct.unpack(
            BZ_FORMAT,
            data[offset:offset + BZ_ENTRY_SIZE]
        )

        result[timestamp] = {
            "MaxSell": max_sell,
            "MinBuy": min_buy,
        }

    return result
def get_single_price(data: dict)->dict:
    return {tz: (values["MaxSell"]+values["MinBuy"])/2 for tz, values in data.items()}
def cut_range(data: dict, start_date: int, end_date: int) -> dict:
    if data=={}:
        return data

    return {
        timestamp: values
        for timestamp, values in data.items()
        if start_date < int(timestamp) <= end_date
    }
def bz_convert(original: list) -> dict:
    new = {}
    i = -1
    s=0
    b=0
    for item in original:
        i+=1
        if "timestamp" not in item:
            print("[ERROR 344] TIMESTAMP NOT IN ITEM")
            continue

        values=clean_prices(item)
        if not values:
            continue
        if "sell" not in values:
            if "maxSell" not in values:
                s+=1
                if "buy" not in values:
                    if "minBuy" not in values:
                        #print("no price found: " + str(i))
                        continue
                    sell=values["minBuy"]
                else:
                    sell = values["buy"]
            else:
                sell=values["maxSell"]
        else:
            sell=values["sell"]
        if "buy" not in values:
            if "minBuy" not in values:
                b+=1
                if "sell" not in values:
                    if "maxSell" not in values:
                        print("no price found: " + str(i))
                        continue
                    buy=values["maxSell"]
                else:
                    buy = values["sell"]
            else:
                buy=values["minBuy"]
        else:
            buy=values["buy"]
        
        dt = datetime.fromisoformat(item["timestamp"]).replace(tzinfo=timezone.utc)
        timestamp = str(int(dt.timestamp()))
        new[timestamp] = {
            "MaxSell": sell,
            "MinBuy": buy,
        }
    if s>0:
        pass#print("SELL NOT FOUND:", s)
    if b>0:
        pass#print("BUY NOT FOUND:", b)
    return new
def ah_convert(original: list) -> dict:
    new = {}
    f=i=0
    for item in original:
        i+=1
        if "time" not in item:
            print("[ERROR 344] TIME NOT IN ITEM")
            continue
        avg = int(item.get("avg", 0))
        volume = int(item.get("volume", 0))
        if avg==0:
            f+=1
            continue
        dt = datetime.fromisoformat(item["time"]).replace(tzinfo=timezone.utc)
        timestamp = str(int(dt.timestamp()))
        new[timestamp] = {
            "avg": avg,
            "volume": volume
        }
    if f>0:
        pass#print("avg not found:", f)
    return new

def clean_prices(item):
    keys = ("maxBuy", "maxSell", "minBuy", "minSell", "buy", "sell")

    values = {
        key: item[key]
        for key in keys
        if key in item and item[key] is not None
    }

    if not values:
        return None

    median = statistics.median(values.values())

    # Ignore values more than 50% away from the median
    values = {
        key: value
        for key, value in values.items()
        if median * 0.4 <= value <= median * 1.6
    }
    return values
def append_new_data(data: dict, path: str):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "wb") as f:
            f.write(to_bytes(data))
        return
    with open(path, "rb") as f:
        f.seek(-BZ_ENTRY_SIZE, 2)
        last_entry = f.read(BZ_ENTRY_SIZE)
    timestamp, maxSell, minBuy = struct.unpack(BZ_FORMAT, last_entry)
    new_data = cut_range(data, start_date=timestamp, end_date=next(reversed(data)))
    with open(path, "ab") as f:
        f.write(to_bytes(new_data))
def insert_bz_data(data: dict, path: str):
    new_data = sorted(
        ((int(timestamp), int(values["MaxSell"]), int(values["MinBuy"]))
         for timestamp, values in data.items()),
        key=lambda x: x[0]
    )
    if not new_data:
        return
    # No existing file
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "wb") as f:
            for record in new_data:
                f.write(struct.pack(BZ_FORMAT, *record))
        return

    # Read existing records
    with open(path, "rb") as f:
        existing = []
        while chunk := f.read(BZ_ENTRY_SIZE):
            existing.append(struct.unpack(BZ_FORMAT, chunk))

    # Merge existing + new data
    merged = []
    i = j = 0
    while i < len(existing) and j < len(new_data):
        if existing[i][0] < new_data[j][0]:
            merged.append(existing[i])
            i += 1
        elif existing[i][0] > new_data[j][0]:
            merged.append(new_data[j])
            j += 1
        else:
            # Same timestamp: replace existing
            merged.append(new_data[j])
            i += 1
            j += 1
    merged.extend(existing[i:])
    merged.extend(new_data[j:])
    # Rewrite file
    with open(path, "wb") as f:
        for record in merged:
            f.write(struct.pack(BZ_FORMAT, int(record[0]), int(record[1]), int(record[2])))
def insert_ah_data(data: dict, path: str):
    new_data = sorted(
        ((int(timestamp), int(values["avg"]), int(values["volume"]))
         for timestamp, values in data.items()),
        key=lambda x: x[0]
    )
    if not new_data:
        return
    # No existing file
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "wb") as f:
            for record in new_data:
                f.write(struct.pack(AH_FORMAT, *record))
        return


    # Read existing records
    with open(path, "rb") as f:
        existing = []
        while chunk := f.read(AH_ENTRY_SIZE):
            existing.append(struct.unpack(AH_FORMAT, chunk))

    # Merge existing + new data
    merged = []
    i = j = 0
    while i < len(existing) and j < len(new_data):
        if existing[i][0] < new_data[j][0]:
            merged.append(existing[i])
            i += 1
        elif existing[i][0] > new_data[j][0]:
            merged.append(new_data[j])
            j += 1
        else:
            # Same timestamp: replace existing
            merged.append(new_data[j])
            i += 1
            j += 1
    merged.extend(existing[i:])
    merged.extend(new_data[j:])
    # Rewrite file
    with open(path, "wb") as f:
        for record in merged:
            f.write(struct.pack(AH_FORMAT, int(record[0]), int(record[1]), int(record[2])))

#manual helper
def remove_timestamp(timestamp: int, path: str):
    with open(path, "rb") as f:
        f.seek(0, 2)
        num_entries = f.tell() // BZ_ENTRY_SIZE
        low = 0
        high = num_entries - 1
        while low < high:
            mid = (low + high) // 2
            f.seek(mid * BZ_ENTRY_SIZE)
            curr_timestamp = struct.unpack("<q", f.read(8))[0]
            if curr_timestamp < timestamp:
                low = mid + 1
            else:
                high = mid
        index = low
        f.seek(index * BZ_ENTRY_SIZE)
        if struct.unpack("<q", f.read(8))[0]!=timestamp:
            print("COULD NOT FIND timestamp: '"+str(timestamp)+"' in path: '"+path+"'")
            return

    with open(path, "rb") as src, open(path + ".tmp", "wb") as dst:
        dst.write(src.read(index * BZ_ENTRY_SIZE))
        src.seek(16, 1)
        while chunk := src.read(1024 * 1024):
            dst.write(chunk)
    os.replace(path + ".tmp", path)
    print("SUCCESSFULLY REMOVED timestamp: '"+str(timestamp)+"'")
def replace_timestamp(timestamp: int, path: str, value: int):
    with open(path, "rb") as f:
        f.seek(0, 2)
        num_entries = f.tell() // BZ_ENTRY_SIZE
        low = 0
        high = num_entries - 1
        while low < high:
            mid = (low + high) // 2
            f.seek(mid * BZ_ENTRY_SIZE)
            curr_timestamp = struct.unpack("<q", f.read(8))[0]
            if curr_timestamp < timestamp:
                low = mid + 1
            else:
                high = mid
        index = low
        f.seek(index * BZ_ENTRY_SIZE)
        if struct.unpack("<q", f.read(8))[0]!=timestamp:
            print("COULD NOT FIND timestamp: '"+str(timestamp)+"' in path: '"+path+"'")
            return
    with open(path, "r+b") as f:
        f.seek(index * BZ_ENTRY_SIZE)
        f.write(to_bytes({str(timestamp): {"MaxSell": value, "MinBuy": value}}))
    print("SUCCESSFULLY REPLACED TIMESTAMP")

#/bzItems/ + /ahItems  GET
def get_item(path: str, start_date: int, end_date: int, interval: int, type:str="bz") -> dict:
    result = {}
    next_timestamp = start_date
    with open(path, "rb") as f:
        if type=="bz":
            while True:
                data = f.read(BZ_ENTRY_SIZE)
                if len(data) < BZ_ENTRY_SIZE:
                    break
                timestamp, max_sell, min_buy = struct.unpack(BZ_FORMAT, data)
                if timestamp > end_date:
                    break
                if timestamp >= next_timestamp:
                    result[timestamp] = {
                        "MaxSell": max_sell,
                        "MinBuy": min_buy,
                    }
                    next_timestamp = timestamp + interval
        else:
            while True:
                data = f.read(AH_ENTRY_SIZE)
                if len(data) < AH_ENTRY_SIZE:
                    break
                timestamp, avg, volume = struct.unpack(AH_FORMAT, data)
                if timestamp > end_date:
                    break
                if timestamp >= next_timestamp:
                    result[timestamp] = avg
                    next_timestamp = timestamp + interval
    return result
def get_item_fast(path: str, start_date: int, end_date: int, interval: int, type:str="bz") -> dict:
    result = {}
    with open(path, "rb") as f:
        if type=="bz":
            f.seek(0, 2)
            num_entries = f.tell() // BZ_ENTRY_SIZE
            if num_entries == 0:
                return result
            # Binary search for first timestamp >= start_date
            low = 0
            high = num_entries - 1
            while low < high:
                mid = (low + high) // 2
                f.seek(mid * BZ_ENTRY_SIZE)
                timestamp = struct.unpack("<q", f.read(8))[0]
                if timestamp < start_date:
                    low = mid + 1
                else:
                    high = mid

            index = low
            f.seek(index * BZ_ENTRY_SIZE)
            next_timestamp = start_date
            while index < num_entries:
                data = f.read(BZ_ENTRY_SIZE)
                if len(data) < BZ_ENTRY_SIZE:
                    break
                timestamp, max_sell, min_buy = struct.unpack(BZ_FORMAT, data)
                if timestamp > end_date:
                    break
                if timestamp >= next_timestamp:
                    result[timestamp] = {
                        "MaxSell": max_sell,
                        "MinBuy": min_buy,
                    }
                    next_timestamp = timestamp + interval
                index += 1
        else:
            f.seek(0, 2)
            num_entries = f.tell() // AH_ENTRY_SIZE
            if num_entries == 0:
                return result
            # Binary search for first timestamp >= start_date
            low = 0
            high = num_entries - 1
            while low < high:
                mid = (low + high) // 2
                f.seek(mid * AH_ENTRY_SIZE)
                timestamp = struct.unpack("<q", f.read(8))[0]
                if timestamp < start_date:
                    low = mid + 1
                else:
                    high = mid

            index = low
            f.seek(index * AH_ENTRY_SIZE)
            next_timestamp = start_date
            while index < num_entries:
                data = f.read(AH_ENTRY_SIZE)
                if len(data) < AH_ENTRY_SIZE:
                    break
                timestamp, avg, volume = struct.unpack(BZ_FORMAT, data)
                if timestamp > end_date:
                    break
                if timestamp >= next_timestamp:
                    result[timestamp] = {
                        "avg": avg,
                        "volume": volume
                    }
                    next_timestamp = timestamp + interval
                index += 1
    return result

#/bzItems/  history  DOWNLOAD
def download_bz_item_this_hour(item):
    data_dict = bz_convert(requests.get(f"https://sky.coflnet.com/api/bazaar/{item}/history/hour").json())
    insert_bz_data(data_dict, f"data/bzItems/{item}.dat")
def download_bz_item_today(item):
    data_dict = bz_convert(requests.get(f"https://sky.coflnet.com/api/bazaar/{item}/history/day").json())
    insert_bz_data(data_dict, f"data/bzItems/{item}.dat")
def download_bz_item_this_week(item):
    data_dict = bz_convert(requests.get(f"https://sky.coflnet.com/api/bazaar/{item}/history/week").json())
    insert_bz_data(data_dict, f"data/bzItems/{item}.dat")
def download_bz_item_history(item)->bool:
    try:
        data = requests.get(f"https://sky.coflnet.com/api/bazaar/{item}/history")
        if data.status_code!=200:
            print("[ERROR 253] STATUS CODE NOT 200!")
            return False
        data_js = data.json()
        if not data_js:
            return False
        converted = bz_convert(data_js)
        insert_bz_data(converted, f"data/bzItems/{item}.dat")
        return True
    except Exception as e:
        print(e)
        return False
    
#/ahItems/  history  DOWNLOAD
def download_ah_item_today(item):
    data_dict = ah_convert(requests.get(f"https://sky.coflnet.com/api/item/price/{item}/history/day").json())
    insert_ah_data(data_dict, f"data/ahItems/{item}.dat")
def download_ah_item_this_week(item):
    data_dict = ah_convert(requests.get(f"https://sky.coflnet.com/api/item/price/{item}/history/week").json())
    insert_ah_data(data_dict, f"data/ahItems/{item}.dat")
def download_ah_item_this_month(item):
    data_dict = ah_convert(requests.get(f"https://sky.coflnet.com/api/item/price/{item}/history/month").json())
    insert_ah_data(data_dict, f"data/ahItems/{item}.dat")
def download_ah_item_this_year(item):
    data_dict = ah_convert(requests.get(f"https://sky.coflnet.com/api/item/price/{item}/history/year").json())
    insert_ah_data(data_dict, f"data/ahItems/{item}.dat")
def download_ah_item_history(item)->bool:
    try:
        data = requests.get(f"https://sky.coflnet.com/api/item/price/{item}/history/full")
        if data.status_code!=200:
            print("[ERROR 253] STATUS CODE NOT 200!")
            return False
        data_js = data.json()
        if not data_js:
            return False
        insert_ah_data(ah_convert(data_js), f"data/ahItems/{item}.dat")
        return True
    except Exception as e:
        print(e)
        return False

#/other/
def download_all_items():
    path="data/other/items.json"
    data=requests.get("https://api.hypixel.net/v2/resources/skyblock/items").json()
    with open(path, "w") as f:
        json.dump(data, f)
def download_bz_items():
    path="data/other/bzitems.json"
    data=requests.get("https://sky.coflnet.com/api/items/bazaar/tags").json()
    with open(path, "w") as f:
        json.dump(data, f)
def index_item_info():
    with open("data/other/items2.json", "r") as f:
        items=json.load(f)
    info={}
    names_existing=[]
    ignored = ["components", "prestige", "description","salvages" ,"gemstone_slots", "skin", "id", "stats", "requirements", "museum_data", "catacombs_requirements", "dungeon_item_conversion_cost", "upgrade_costs", "tiered_stats", "ability_damage_scaling", "item_specific"]
    result={}
    for item in items["items"]:
        if "generator" in item:
            continue
        if ignore_item({"tag": item["id"], "name": item["id"]}):
            continue
        info[item["id"]]={k: v for k, v in item.items() if (k not in ignored)}
        if "skin" in item:
            info[item["id"]]["skin"]=item["skin"]["value"]#Todo: base64decode andextract url
        elif "item_specific" in item and "skin" in item["item_specific"]:
            info[item["id"]]["skin"]=item["item_specific"]["skin"]
            continue
        #result[item["id"]]=len(str(info[item["id"]]))
    #sorted_d = dict(sorted(result.items(), reverse=True, key=lambda x: x[1]))
    with open("data/other/items.json", "w") as f:
        json.dump(info, f)

#live data
def robust_book_price(orders,side="sell",max_distance=0.10,decay=20.0,):
    """
    Estimate fair price from an order book without specifying
    a fixed trade quantity.

    Parameters
    ----------
    orders:
        [{"pricePerUnit": float, "amount": float}, ...]

    side:
        "sell" -> cheapest prices are considered first
        "buy"  -> highest prices are considered first

    max_distance:
        Ignore prices more than this fraction away from
        the best price.

    decay:
        Controls how quickly price-distance reduces influence.
        Higher = stronger preference for prices near the best price.
    """

    if not orders:
        return None
    orders = [o for o in orders if o["pricePerUnit"] > 0 and o["amount"] > 0]

    if not orders:
        return None

    if side == "sell":
        best = min(o["pricePerUnit"] for o in orders)
    else:
        best = max(o["pricePerUnit"] for o in orders)

    weighted_price = 0.0
    total_weight = 0.0

    for order in orders:
        price = order["pricePerUnit"]
        amount = order["amount"]
        if side == "sell":
            distance = (price - best) / best
        else:
            distance = (best - price) / best
        # Ignore extreme outliers
        if distance > max_distance:
            continue
        # Price proximity weight
        price_weight = math.exp(-decay * distance)
        # Liquidity weight, but with diminishing returns.
        # sqrt prevents huge orders from dominating.
        liquidity_weight = amount ** 0.5
        weight = price_weight * liquidity_weight
        weighted_price += price * weight
        total_weight += weight
    if total_weight == 0:
        return best
    return weighted_price / total_weight
def fetch_new_live_bz_data():
    bz_data=requests.get("https://api.hypixel.net/v2/skyblock/bazaar").json()
    if not bz_data["success"]:
        print("[ERROR 325] error while fetching hypixel bz api: " + str(bz_data))
        return
    with open("data/other/bz.json", "w") as f:
        json.dump(bz_data, f)
    ts=str(bz_data["lastUpdated"]//1000)
    for item in bz_data["products"]:
        buy_orders = bz_data["products"][item]["sell_summary"]
        sell_orders = bz_data["products"][item]["buy_summary"]
        buy_price = robust_book_price(buy_orders, "buy")
        sell_price = robust_book_price(sell_orders, "sell")
        if buy_price==None and sell_price==None:
            continue
        if buy_price==None:
            buy_price=sell_price
        if sell_price==None:
            sell_price=buy_price
        #cache instead?
        with open(f"data/bzItems/{item}.dat", "ab") as f:
            f.write(to_bytes({ts: {"MinBuy": buy_price, "MaxSell": sell_price}}))
def fetch_new_live_ah_data():
    response=requests.get(f"https://sky.coflnet.com/api/prices/neu")
    if response.status_code!=200:
        print("[ERROR 325] error while fetching neu ah: " + str(response.content))
        return
    ah_items = response.json()
    with open("data/other/neu.json", "w") as f:
        json.dump(ah_items, f)
    for item in ah_items:
        price = ah_items[item]
        ts=int(time.time())
        #cache instead?
        with open(f"data/ahItems/{item}.dat", "ab") as f:
            f.write(struct.pack(BZ_FORMAT, ts, price))

def save_info():
    with open("data/other/bz.json", "r") as f:
        bz_data:dict=json.load(f)
    if bz_data["lastUpdated"]//1000-time.time()>60*60*2:#2h
        print("bz data old - fetching new one")
        bz_data=requests.get("https://api.hypixel.net/v2/skyblock/bazaar").json()
        with open("data/other/bz.json", "w") as f:
            json.dump(bz_data, f)
    bz_items = bz_data["products"]
    with open("data/other/items.json", "r") as f:
        all_items=json.load(f)
    items={os.path.splitext(item)[0]: "data/bzItems/"+item for item in os.listdir("data/bzItems/")}
    items.update({os.path.splitext(item)[0]: "data/ahItems/"+item for item in os.listdir("data/ahItems/")})
    info={}
    for itemId in items:
        if ignore_item({"tag": itemId, "name": itemId}):
            continue
        bz = itemId in bz_items
        info[itemId]={"itemId": itemId, "startDate": 0, "startPrice": 0, 
        "currentPrice": 0, "currentDate": 0, "change": 0, "changeTimestamp": 0}
        info[itemId]["sellVolume"]= bz_items[itemId]["quick_status"]["sellVolume"] if bz else 0
        info[itemId]["buyVolume"]=bz_items[itemId]["quick_status"]["buyVolume"] if bz else 0
        info[itemId]["sellMovingWeek"]=bz_items[itemId]["quick_status"]["sellMovingWeek"] if bz else 0
        info[itemId]["buyMovingWeek"]=bz_items[itemId]["quick_status"]["buyMovingWeek"] if bz else 0
        info[itemId]["sellOrders"]=bz_items[itemId]["quick_status"]["sellOrders"] if bz else 0
        info[itemId]["buyOrders"]=bz_items[itemId]["quick_status"]["buyOrders"] if bz else 0
        info[itemId]["bz"]= bz
        #info[itemId]["npcSellPrice"]=all_items[itemId].get("npc_sell_price", 0) if bz else 0
        #info[itemId]["skin"]=all_items[itemId].get("kin", "")
        with open(items[itemId], "rb") as f:
            if bz:
                f.seek(0, 2)
                num_entries=f.tell()//BZ_ENTRY_SIZE
                if num_entries<1:
                    continue
                f.seek(0)
                data = f.read(BZ_ENTRY_SIZE)
                if len(data) < BZ_ENTRY_SIZE:#should not happend
                    continue
                timestamp, max_sell, min_buy = struct.unpack(BZ_FORMAT, data)
                info[itemId]["startDate"]= timestamp
                info[itemId]["startPrice"]= (max_sell+min_buy)/2
                f.seek(-BZ_ENTRY_SIZE, 2)
                last_entry = f.read(BZ_ENTRY_SIZE)
                timestamp, max_sell, min_buy = struct.unpack(BZ_FORMAT, last_entry)
                last_price=(max_sell+min_buy)/2
                info[itemId]["currentPrice"]=last_price
                info[itemId]["currentDate"]=timestamp
                start_date=timestamp-24*60*60#24h
                # Binary search
                low = 0
                high = num_entries - 1
                while low <= high:
                    mid = (low + high) // 2
                    f.seek(mid * BZ_ENTRY_SIZE)
                    timestamp = struct.unpack("<q", f.read(8))[0]
                    if timestamp <= start_date:
                        low = mid + 1
                    else:
                        high = mid - 1
                if high < 0:
                    high=0
                f.seek(high * BZ_ENTRY_SIZE)
                prev_day_entry = f.read(BZ_ENTRY_SIZE)
                timestamp, max_sell, min_buy = struct.unpack(BZ_FORMAT, prev_day_entry)
                prev_price=max((max_sell+min_buy)/2, 0.1)
                info[itemId]["change"]=round(((last_price - prev_price) / prev_price) * 100, 2)
                info[itemId]["changeTimestamp"]=timestamp
            else:
                f.seek(0, 2)
                num_entries=f.tell()//AH_ENTRY_SIZE
                if num_entries<1:
                    continue
                f.seek(0)
                data = f.read(AH_ENTRY_SIZE)
                if len(data) < AH_ENTRY_SIZE:#should not happend
                    continue
                timestamp, avg, start_price = struct.unpack(AH_FORMAT, data)
                info[itemId]["startDate"]= timestamp
                info[itemId]["startPrice"]= start_price
                f.seek(-AH_ENTRY_SIZE, 2)
                last_entry = f.read(AH_ENTRY_SIZE)
                timestamp, last_price, volume = struct.unpack(AH_FORMAT, last_entry)
                info[itemId]["currentPrice"]=last_price
                info[itemId]["currentDate"]=timestamp
                info[itemId]["sellVolume"]=volume
                info[itemId]["buyVolume"]=volume
                start_date=timestamp-24*60*60#24h
                # Binary search
                low = 0
                high = num_entries - 1
                while low <= high:
                    mid = (low + high) // 2
                    f.seek(mid * AH_ENTRY_SIZE)
                    timestamp = struct.unpack("<q", f.read(8))[0]
                    if timestamp <= start_date:
                        low = mid + 1
                    else:
                        high = mid - 1
                if high < 0:
                    high=0
                f.seek(high * AH_ENTRY_SIZE)
                prev_day_entry = f.read(AH_ENTRY_SIZE)
                timestamp, price, volume = struct.unpack(AH_FORMAT, prev_day_entry)
                prev_price=max(price, 0.1)
                info[itemId]["change"]=round(((last_price - prev_price) / prev_price) * 100, 2)
                info[itemId]["changeTimestamp"]=timestamp

    with open("data/other/info.json", "w") as f:
        json.dump(info, f)

ignored = ["SPRUCE_FENCE_GATE","ACACIA_FENCE", "POWERED_MINECART", "SANDSTONE_STAIRS"]
def ignore_item(item)->bool:#TODO add vanilla items
    if is_illegal_windows_filename(item["tag"]):
        return True
    if item["tag"].startswith("STARRED_"):
        return True
    if item["name"] == "null" or item["name"]=="None" or not item["name"]:
        return True
    if "_GENERATOR_" in item["tag"]:
        return True
    if item["tag"] in ignored:
        return True
    return False

def download_item_infos():
    response = requests.get(f"https://sky.coflnet.com/api/items")
    if response.status_code!=200:
        return
    data=response.json()
    with open("data/other/AllItems.json", "w") as f:
        json.dump(data, f)

_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

def is_illegal_windows_filename(filename: str) -> bool:
    if not filename:
        return True

    # Cannot end with space or dot
    if filename.endswith((" ", ".")):
        return True

    # Invalid characters
    if _INVALID_CHARS.search(filename):
        return True

    # Reserved device names (with or without extension)
    stem = filename.split(".")[0].upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        return True

    return False

def download_skins():
    data={}
    with open("data/other/AllItems.json", "r") as f:
        ITEMS = json.load(f)
    for item in ITEMS:
        if not item["name"] or not item["tag"]:
            continue
        if "PET_SKIN" in item["tag"]:
            data[item["tag"]] = {"name": item["name"], "type": "PET"}
        elif "Power Orb Skin" in item["name"]:
            data[item["tag"]] = {"name": item["name"], "type": "FLUX"}
        elif " PET" in item["name"]:
            data[item["tag"]] = {"name": item["name"], "type": "HELMET"}
    with open("data/other/skins.json", "w") as f:
        json.dump(data, f)

def convert_skin_data():
    data={}
    with open("data/other/skins.json", "r") as f:
        SKINS = json.load(f)
    for skin in SKINS:
        if not os.path.exists("data/ahItems/"+skin+".dat"):
            continue
        data[skin]=get_item("data/ahItems/"+skin+".dat", 0, int(time.time()), 0, type="ah")
    with open("data/other/SkinData.json", "w") as f:
        json.dump(data, f)


#item="BONZO_MASK"
#print(get_item(f"data/ahItems/{item}.dat", start_date, end_date, interval, "ah"))
#save_info()
quit()

if __name__ == "__main__":
    print("DOWNLOAD DATA")
    try:
        with open("data/other/IGNORED.json", "r") as f:
            IGNORED:list= json.load(f)
    except Exception as e:
        IGNORED = []
        with open("data/other/IGNORED.json", "w") as f:
            json.dump([], f)
    with open("data/other/AllItems.json", "r") as f:
        ITEMS = json.load(f)
    with open("data/other/bzItems.json", "r") as f:
        BZ_ITEMS = json.load(f)
    AH_ITEMS_HAVE=[item.removesuffix(".dat") for item in os.listdir("data/ahItems/")]
    #AH_ITEMS_HAVE = [item.removesuffix(".dat") for item in os.listdir("data/ahItems/") if (os.path.exists("data/ahItems/"+item) and os.path.getsize("data/ahItems/"+item)>2*1024)]
    BZ_ITEMS_HAVE = [item.removesuffix(".dat") for item in os.listdir("data/bzItems/") if (os.path.exists("data/bzItems/"+item) and os.path.getsize("data/bzItems/"+item))>2*1024]
    ALL_ITEMS_HAVE = AH_ITEMS_HAVE+BZ_ITEMS_HAVE

    total_amount = len(ITEMS)
    have_amount=0#len(ALL_ITEMS_HAVE)

    for item in ITEMS:
        try:
            have_amount+=1
            if ignore_item(item) or item["tag"] in IGNORED:
                continue
            if item["tag"] in ALL_ITEMS_HAVE:
                continue
            print(item["tag"])
            flags = item["flags"]
            if not flags or flags == "NONE":
                continue
            if item["tag"] in BZ_ITEMS:
                result = download_bz_item_history(item["tag"])
            else:
                result = download_ah_item_history(item["tag"])
            if not result:
                print("ADD TO IGNORE")
                IGNORED.append(item["tag"])
                with open("data/other/IGNORED.json", "w") as f:
                    json.dump(IGNORED, f)
            print(f"{round((have_amount/total_amount)*100, 2)}%")
            time.sleep(0.6)
        except Exception as e:
            print(e)
            quit(1)

#download_ah_item_today("SUPERIOR_DRAGON_CHESTPLATE")
#download_ah_item_this_month("SUPERIOR_DRAGON_CHESTPLATE")

#print(get_item("data/ahItems/SUPERIOR_DRAGON_CHESTPLATE.dat",0, int(time.time()), 0, type="ah"))


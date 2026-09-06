import requests, os, json, struct, math, time, statistics
from datetime import datetime, timezone

# int64 timestamp + int32 MaxSell + int32 MinBuy
FORMAT = "<qii"
ENTRY_SIZE = struct.calcsize(FORMAT)  # 16 bytes

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
            FORMAT,
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
    if len(data) % ENTRY_SIZE != 0:
        raise ValueError(
            f"Invalid data length: {len(data)} bytes "
            f"(must be a multiple of {ENTRY_SIZE})"
        )

    result = {}

    for offset in range(0, len(data), ENTRY_SIZE):
        timestamp, max_sell, min_buy = struct.unpack(
            FORMAT,
            data[offset:offset + ENTRY_SIZE]
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
def convert(original: list) -> dict:
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
        if "sell" not in values:
            if "maxSell" not in values:
                s+=1
                if "buy" not in values:
                    if "minBuy" not in values:
                        print("no price found: " + str(i))
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
        print("SELL NOT FOUND:", s)
    if b>0:
        print("BUY NOT FOUND:", b)
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
        f.seek(-ENTRY_SIZE, 2)
        last_entry = f.read(ENTRY_SIZE)
    timestamp, maxSell, minBuy = struct.unpack(FORMAT, last_entry)
    new_data = cut_range(data, start_date=timestamp, end_date=next(reversed(data)))
    with open(path, "ab") as f:
        f.write(to_bytes(new_data))
def insert_data(data: dict, path: str):
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
                f.write(struct.pack(FORMAT, *record))
        return

    # Read existing records
    with open(path, "rb") as f:
        existing = []
        while chunk := f.read(ENTRY_SIZE):
            existing.append(struct.unpack(FORMAT, chunk))

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
            f.write(struct.pack(FORMAT, int(record[0]), int(record[1]), int(record[2])))

#manual helper
def remove_timestamp(timestamp: int, path: str):
    with open(path, "rb") as f:
        f.seek(0, 2)
        num_entries = f.tell() // ENTRY_SIZE
        low = 0
        high = num_entries - 1
        while low < high:
            mid = (low + high) // 2
            f.seek(mid * ENTRY_SIZE)
            curr_timestamp = struct.unpack("<q", f.read(8))[0]
            if curr_timestamp < timestamp:
                low = mid + 1
            else:
                high = mid
        index = low
        f.seek(index * ENTRY_SIZE)
        if struct.unpack("<q", f.read(8))[0]!=timestamp:
            print("COULD NOT FIND timestamp: '"+str(timestamp)+"' in path: '"+path+"'")
            return

    with open(path, "rb") as src, open(path + ".tmp", "wb") as dst:
        dst.write(src.read(index * ENTRY_SIZE))
        src.seek(16, 1)
        while chunk := src.read(1024 * 1024):
            dst.write(chunk)
    os.replace(path + ".tmp", path)
    print("SUCCESSFULLY REMOVED timestamp: '"+str(timestamp)+"'")
def replace_timestamp(timestamp: int, path: str, value: int):
    with open(path, "rb") as f:
        f.seek(0, 2)
        num_entries = f.tell() // ENTRY_SIZE
        low = 0
        high = num_entries - 1
        while low < high:
            mid = (low + high) // 2
            f.seek(mid * ENTRY_SIZE)
            curr_timestamp = struct.unpack("<q", f.read(8))[0]
            if curr_timestamp < timestamp:
                low = mid + 1
            else:
                high = mid
        index = low
        f.seek(index * ENTRY_SIZE)
        if struct.unpack("<q", f.read(8))[0]!=timestamp:
            print("COULD NOT FIND timestamp: '"+str(timestamp)+"' in path: '"+path+"'")
            return
    with open(path, "r+b") as f:
        f.seek(index * ENTRY_SIZE)
        f.write(to_bytes({str(timestamp): {"MaxSell": value, "MinBuy": value}}))
    print("SUCCESSFULLY REPLACED TIMESTAMP")

#/bzItems/ + /ahItems
def get_item(path: str, start_date: int, end_date: int, interval: int) -> dict:
    result = {}
    next_timestamp = start_date
    with open(path, "rb") as f:
        while True:
            data = f.read(ENTRY_SIZE)
            if len(data) < ENTRY_SIZE:
                break
            timestamp, max_sell, min_buy = struct.unpack(FORMAT, data)
            if timestamp > end_date:
                break
            if timestamp >= next_timestamp:
                result[timestamp] = {
                    "MaxSell": max_sell,
                    "MinBuy": min_buy,
                }
                next_timestamp = timestamp + interval
    return result
def get_item_fast(path: str, start_date: int, end_date: int, interval: int) -> dict:
    result = {}
    with open(path, "rb") as f:
        f.seek(0, 2)
        num_entries = f.tell() // ENTRY_SIZE
        if num_entries == 0:
            return result
        # Binary search for first timestamp >= start_date
        low = 0
        high = num_entries - 1
        while low < high:
            mid = (low + high) // 2
            f.seek(mid * ENTRY_SIZE)
            timestamp = struct.unpack("<q", f.read(8))[0]
            if timestamp < start_date:
                low = mid + 1
            else:
                high = mid

        index = low
        f.seek(index * ENTRY_SIZE)
        next_timestamp = start_date
        while index < num_entries:
            data = f.read(ENTRY_SIZE)
            if len(data) < ENTRY_SIZE:
                break
            timestamp, max_sell, min_buy = struct.unpack(FORMAT, data)
            if timestamp > end_date:
                break
            if timestamp >= next_timestamp:
                result[timestamp] = {
                    "MaxSell": max_sell,
                    "MinBuy": min_buy,
                }
                next_timestamp = timestamp + interval
            index += 1
    return result

#/bzItems/  history
def download_item_this_hour(item):
    data_dict = convert(requests.get(f"https://sky.coflnet.com/api/bazaar/{item}/history/hour").json())
    insert_data(data_dict, f"data/bzItems/{item}.dat")
def download_item_today(item):
    data_dict = convert(requests.get(f"https://sky.coflnet.com/api/bazaar/{item}/history/day").json())
    insert_data(data_dict, f"data/bzItems/{item}.dat")
def download_item_this_week(item):
    data_dict = convert(requests.get(f"https://sky.coflnet.com/api/bazaar/{item}/history/week").json())
    insert_data(data_dict, f"data/bzItems/{item}.dat")
def download_item_history(item):
    data = requests.get(f"https://sky.coflnet.com/api/bazaar/{item}/history")
    if data.status_code!=200:
        print("[ERROR 253] STATUS CODE NOT 200!")
        return
    insert_data(convert(data.json()), f"data/bzItems/{item}.dat")

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
    ignored = ["components", "prestige", "description","salvages" ,"gemstone_slots", "skin", "id", "stats", "requirements", "museum_data", "catacombs_requirements", "dungeon_item_conversion_cost", "upgrade_costs", "tiered_stats", "ability_damage_scaling", "item_specific"]
    result={}
    for item in items["items"]:
        if "generator" in item:
            continue
        info[item["id"]]={k: v for k, v in item.items() if (k not in ignored)}
        if "skin" in item:
            info[item["id"]]["skin"]=item["skin"]["value"]
        elif "item_specific" in item and "skin" in item["item_specific"]:
            info[item["id"]]["skin"]=item["item_specific"]["skin"]
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

def save_info():
    with open("data/other/bz.json", "r") as f:
        bz_data:dict=json.load(f)
    if bz_data["lastUpdated"]//1000-time.time()>60*60*2:#2h
        print("bz data old - fetching new one")
        bz_data=requests.get("https://api.hypixel.net/v2/skyblock/bazaar").json()
        with open("data/other/bz.json", "w") as f:
            json.dump(bz_data, f)
    bz_items = bz_data["products"]
    items={os.path.splitext(item)[0]: "data/bzItems/"+item for item in os.listdir("data/bzItems/")}
    items.update({os.path.splitext(item)[0]: "data/ahItems/"+item for item in os.listdir("data/ahItems/")})
    info={}
    for itemId in items:
        info[itemId]={"itemId": itemId, "startDate": 0, "startPrice": 0, 
        "currentPrice": 0, "currentDate": 0, "change": 0, "changeTimestamp": 0}
        info[itemId]["sellVolume"]=bz_items[itemId]["quick_status"]["sellVolume"]
        info[itemId]["buyVolume"]=bz_items[itemId]["quick_status"]["buyVolume"]
        info[itemId]["sellMovingWeek"]=bz_items[itemId]["quick_status"]["sellMovingWeek"]
        info[itemId]["buyMovingWeek"]=bz_items[itemId]["quick_status"]["buyMovingWeek"]
        info[itemId]["sellOrders"]=bz_items[itemId]["quick_status"]["sellOrders"]
        info[itemId]["buyOrders"]=bz_items[itemId]["quick_status"]["buyOrders"]
        with open(items[itemId], "rb") as f:
            f.seek(0, 2)
            num_entries=f.tell()//ENTRY_SIZE
            if num_entries<1:
                continue
            f.seek(0)
            data = f.read(ENTRY_SIZE)
            if len(data) < ENTRY_SIZE:#should not happend
                continue
            timestamp, max_sell, min_buy = struct.unpack(FORMAT, data)
            info[itemId]["startDate"]= timestamp
            info[itemId]["startPrice"]= (max_sell+min_buy)/2
            f.seek(-ENTRY_SIZE, 2)
            last_entry = f.read(ENTRY_SIZE)
            timestamp, max_sell, min_buy = struct.unpack(FORMAT, last_entry)
            last_price=(max_sell+min_buy)/2
            info[itemId]["currentPrice"]=last_price
            info[itemId]["currentDate"]=timestamp
            start_date=timestamp-24*60*60#24h
            # Binary search
            low = 0
            high = num_entries - 1
            while low <= high:
                mid = (low + high) // 2
                f.seek(mid * ENTRY_SIZE)
                timestamp = struct.unpack("<q", f.read(8))[0]
                if timestamp <= start_date:
                    low = mid + 1
                else:
                    high = mid - 1
            if high < 0:
                high=0
            f.seek(high * ENTRY_SIZE)
            prev_day_entry = f.read(ENTRY_SIZE)
            timestamp, max_sell, min_buy = struct.unpack(FORMAT, prev_day_entry)
            prev_price=max((max_sell+min_buy)/2, 0.1)
            info[itemId]["change"]=((last_price - prev_price) / prev_price) * 100
            info[itemId]["changeTimestamp"]=timestamp
    with open("data/other/info.json", "w") as f:
        json.dump(info, f)


from flask import Flask, render_template, jsonify, request
import json, hashlib, api
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__, static_folder=None)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///portfolio.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    holdings = db.relationship(
        "Holding",
        backref="portfolio",
        cascade="all, delete-orphan"
    )

class Holding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(
        db.Integer,
        db.ForeignKey("portfolio.id"),
        nullable=False
    )
    item_id = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    price_per_unit = db.Column(db.Float, nullable=False)

if False:#only once
    with app.app_context():
        db.create_all()


with open("data/other/items.json", "r") as f:
    ITEMS = json.load(f)
with open("data/other/bzitems.json", "r") as f:
    BZITEMS = json.load(f)
with open("data/other/info.json", "r") as f:
    INFO = json.load(f)

def to_json_holding(holding: Holding)->dict:
    return {
            "id": holding.id,
            "itemId": holding.item_id,
            "date": holding.date,
            "amount": holding.amount,
            "pricePerUnit": holding.price_per_unit,
            "portfolio_id": holding.portfolio_id
    }

def to_json_portfolio(portfolio: Portfolio)->dict:
    holdings = Holding.query.filter_by(portfolio_id=portfolio.id).all()
    return {
            "id": portfolio.id,
            "name": portfolio.name,
            "description": portfolio.description,
            "holdings": [to_json_holding(holding) for holding in holdings]
    }

@app.route("/api/portfolios/<int:portfolio_id>/holdings", methods=["POST"])
def add_holding(portfolio_id):
    data = request.json
    holding = Holding(
        portfolio_id=portfolio_id,
        item_id=data["itemId"],
        date=data["date"],
        amount=data["amount"],
        price_per_unit=data["pricePerUnit"]
    )
    db.session.add(holding)
    db.session.commit()
    return jsonify({"portfolio_id": portfolio_id, "id": holding.id, "date": data["date"], "itemId": data["itemId"], "amount": data["amount"], "pricePerUnit": data["pricePerUnit"]}), 201
@app.route("/api/portfolios/<int:portfolio_id>/holdings/<int:holding_id>", methods=["PUT"])
def edit_holding(portfolio_id, holding_id):
    holding = Holding.query.filter_by(
        id=holding_id,
        portfolio_id=portfolio_id
    ).first_or_404()
    data = request.json
    holding.item_id = data["itemId"]
    holding.date = data["date"]
    holding.amount = data["amount"]
    holding.price_per_unit = data["pricePerUnit"]
    db.session.commit()
    return jsonify({"Success": True, "message": "Holding updated"})
@app.route("/api/portfolios/<int:portfolio_id>/holdings/<int:holding_id>", methods=["DELETE"])
def remove_holding(portfolio_id, holding_id):
    holding = Holding.query.filter_by(
        id=holding_id,
        portfolio_id=portfolio_id
    ).first_or_404()
    db.session.delete(holding)
    db.session.commit()
    return jsonify({"Success": True,"message": "Holding deleted"})

@app.route("/api/portfolios", methods=["POST"])
def create_portfolio():
    data = request.get_json()
    portfolio = Portfolio(
        name=data["name"],
        description=data.get("description")
    )
    db.session.add(portfolio)
    db.session.commit()
    return jsonify({"id": portfolio.id, "name": data["name"], "description": data["description"], "holdings": []}), 201
@app.route("/api/portfolios/<int:portfolio_id>", methods=["PUT"])
def edit_portfolio(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    data = request.json
    portfolio.name = data["name"]
    portfolio.description = data.get("description")
    db.session.commit()
    return jsonify({"id": portfolio.id, "name": data["name"], "description": data["description"], "holdings": []}), 201
@app.route("/api/portfolios/<int:portfolio_id>", methods=["DELETE"])
def remove_portfolio(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    db.session.delete(portfolio)
    db.session.commit()
    return jsonify({"Success": True,"message": "Portfolio deleted"})

@app.route("/api/get_info/<item>", methods=["GET"])
def get_info(item):
    if item in INFO:
        return jsonify(INFO[item])
    else:
        return jsonify({"Success": False, "message": "could not find item with ItemID: '" + item+"'"})

@app.route("/api/get_infos", methods=["POST"])
def get_infos():
    data=request.get_json()
    items=data.get("itemIds", [])
    result={}
    for item in items:
        if item in INFO:
            result[item]=INFO[item]
    return jsonify(result)


@app.route("/")
def index():
    app.jinja_env.cache = {}#reloads templates
    #items=[{ "id": "BOOSTER_COOKIE", "symbol": "BCK", "name": "booster cookie", "COLOR": "#D9A441" }]
    items=[]
    for itemId in ITEMS:
        if itemId not in BZITEMS and itemId!="SUPERIOR_DRAGON_CHESTPLATE":
            pass#continue#for now only bz
        items.append({"id": itemId, "symbol": itemId[0:3], "name": ITEMS[itemId]["name"], "COLOR": "#"+hashlib.sha256(itemId.encode()).hexdigest()[:6]})
    portfolios = [to_json_portfolio(portfolio) for portfolio in Portfolio.query.all()]
    return render_template("index.html", items=items, portfolios=portfolios)

@app.route("/api/get_range/<item>")
def get_range(item):
    start_date=int(request.args.get("start_date", "0"))
    end_date=int(request.args.get("end_date", "0"))
    interval=int(request.args.get("interval", "0"))
    if item in BZITEMS:
        return jsonify(api.get_single_price(api.get_item(f"data/bzItems/{item}.dat", start_date, end_date, interval, "bz")))
    else:
        return jsonify(api.get_item(f"data/ahItems/{item}.dat", start_date, end_date, interval, "ah"))
    

@app.route("/api/get_all/<item>")
def get_all(item):
    if item in BZITEMS:
        item_ranged = api.get_item(f"data/bzItems/{item}.dat", 0, int(api.time.time())+100, 0)
    else:
        item_ranged = api.get_item(f"data/ahItems/{item}.dat", 0, int(api.time.time())+100, 0)
    return jsonify(api.get_single_price(item_ranged))

if __name__ == '__main__':
    app.run(host="127.0.6.8", port=1234, debug=False)
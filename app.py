from flask import Flask, request, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from marshmallow import fields, validate, validates, ValidationError

import logging
from logging.handlers import RotatingFileHandler
"""using flask, SQLAlchemy and python for the backend, trying to adjust to the tools we spoke over the phone,
as a way of serializing and deserializing I used Marshmallow since it has a smooth integration with Flask. 
Also, as for the load balancer, I would have used ngnix. I added some logging so we can track when and who added the data.
For the ease of work, I will not be moving the code to multiple
files as I would do in a normal project, just so it is easier to read and follow. Models are in the same file as the
flask application, same for views. in a normal world case scenario, this project should be dockerized and run as a 
container. Initiating the database and server in bash."""


app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'

db = SQLAlchemy(app)

ma = Marshmallow(app)

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        RotatingFileHandler("app.log", maxBytes=100000, backupCount=10),
        logging.StreamHandler()
    ],
)


# Database Models
class Site(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=False)

    config = db.relationship('Configuration', backref='site', lazy=True)
    live_data = db.relationship('LiveData', backref='site', lazy=True)


class Battery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    vendor = db.Column(db.String(50), nullable=False)
    capacity_kwh = db.Column(db.Float, nullable=False)
    max_power_kw = db.Column(db.Float, nullable=False)


class ProductionUnit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unit_type = db.Column(db.String(50), nullable=False)
    units = db.Column(db.Integer, nullable=False)
    kwp = db.Column(db.Float, nullable=True)
    configuration_id = db.Column(db.Integer, db.ForeignKey('configuration.id'), nullable=False)


class Configuration(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)

    battery_id = db.Column(db.Integer, db.ForeignKey('battery.id'), nullable=True)
    battery = db.relationship('Battery', backref=db.backref('configurations', lazy=True))

    production_units = db.relationship('ProductionUnit', backref='configuration', lazy=True)


class LiveData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('site.id'), nullable=False)

    dt_stamp = db.Column(db.String(100), nullable=False)
    soc = db.Column(db.Float, nullable=False)
    load_kwh = db.Column(db.Float, nullable=False)
    net_load_kwh = db.Column(db.Float, nullable=False)
    pv_notification = db.Column(db.Boolean, nullable=False)
    bio_notification = db.Column(db.Boolean, nullable=False)
    cro_notification = db.Column(db.Boolean, nullable=False)


# Database setup, remove this line from models.py in production
with app.app_context():
    db.create_all()


# adding validation
class BatterySchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Battery
        load_instance = True

    # validate kw cant be negative
    capacity_kwh = fields.Float(validate=validate.Range(min=0))
    max_power_kw = fields.Float(validate=validate.Range(min=0))

    # lets make sure vendors are the ones we can accept.
    @validates('vendor')
    def validate_vendor(self, value):
        if value not in ["Tesla", "KATL"]:
            raise ValidationError('Vendor must be either "Tesla" or "KATL".')


class ProductionUnitSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = ProductionUnit
        load_instance = True
    # validate units cant be negative
    units = fields.Integer(validate=validate.Range(min=0))


class ConfigurationSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Configuration
        include_relationships = True
        load_instance = True

    battery = ma.Nested(BatterySchema)
    production_units = ma.Nested(ProductionUnitSchema, many=True)


class LiveDataSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = LiveData
        load_instance = True

    # adding validation for all fields
    soc = fields.Float(validate=validate.Range(min=0, max=100))
    load_kwh = fields.Float(validate=validate.Range(min=0))
    net_load_kwh = fields.Float(validate=validate.Range(min=0))
    pv_notification = fields.Boolean()
    bio_notification = fields.Boolean()
    cro_notification = fields.Boolean()


class SiteSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Site
        include_relationships = True
        load_instance = True

    config = ma.Nested(ConfigurationSchema)
    live_data = ma.Nested(LiveDataSchema)


# error handler with logging
def error_response(status_code, message):
    logging.error(f"Error {status_code}: {message}")
    response = make_response(jsonify({"error": message}), status_code)
    return response


# endpoints
@app.route('/api/sites', methods=['GET'])
def get_sites():
    sites = Site.query.all()
    schema = SiteSchema(many=True)
    return jsonify(schema.dump(sites))


@app.route('/api/sites', methods=['POST'])
def create_site():
    try:
        data = request.get_json()
        schema = SiteSchema()
        site = schema.load(data)
        db.session.add(site)
        db.session.commit()
        logging.info(f"New site created: {site.id}")
        return jsonify(schema.dump(site)), 201
    except ValidationError as e:
        return error_response(400, str(e))
    except Exception as e:
        return error_response(500, str(e))


@app.route('/api/configurations', methods=['GET'])
def get_configurations():
    configs = Configuration.query.all()
    schema = ConfigurationSchema(many=True)
    return jsonify(schema.dump(configs))


@app.route('/api/configurations', methods=['POST'])
def create_configuration():
    try:
        data = request.get_json()
        site_id = data["site_id"]

        battery_data = data["battery"]
        battery = Battery(vendor=battery_data['vendor'], capacity_kwh=battery_data['capacity_kwh'], max_power_kw=battery_data['max_power_kw'])
        db.session.add(battery)

        config = Configuration(site_id=site_id, battery=battery)
        for unit_data in data["production_units"]:
            unit = ProductionUnit(unit_type=unit_data['unit_type'], units=unit_data['units'], kwp=unit_data.get('kwp', None))
            config.production_units.append(unit)
            db.session.add(unit)

        db.session.add(config)
        db.session.commit()

        schema = ConfigurationSchema()
        logging.info(f"New configuration created: {config.id}")
        return jsonify(schema.dump(config))
    except Exception as e:
        return error_response(500, str(e))


@app.route('/api/live_data', methods=['GET'])
def get_live_data():
    live_data = LiveData.query.all()
    schema = LiveDataSchema(many=True)
    logging.info("Live data fetched")
    return jsonify(schema.dump(live_data))


@app.route('/api/live_data', methods=['POST'])
def create_live_data():
    try:
        data = request.get_json()

        live_data = LiveData(
            site_id=data['site_id'],
            dt_stamp=data['dt_stamp'],
            soc=data['soc'],
            load_kwh=data['load_kwh'],
            net_load_kwh=data['net_load_kwh'],
            pv_notification=data['pv_notification'],
            bio_notification=data['bio_notification'],
            cro_notification=data['cro_notification']
        )

        db.session.add(live_data)
        db.session.commit()

        schema = LiveDataSchema()
        logging.info(f"New configuration created: {live_data.id}")
        return jsonify(schema.dump(live_data))
    except ValidationError as e:
        return error_response(400, str(e))


if __name__ == '__main__':
    app.run(host="localhost", port=8080, debug=True)


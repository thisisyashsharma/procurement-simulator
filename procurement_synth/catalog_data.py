"""Static, fully synthetic reference vocabularies (no external data sources).

Any resemblance of generated people or company names to real entities is coincidental.
"""

DIVISIONS = ("CORPORATE", "TECHNOLOGY", "OPERATIONS", "COMMERCIAL")

# code, name, cost centre, division, demand weight, headcount weight, category affinity
DEPARTMENTS = [
    ("Executive Office", "CORPORATE", 0.3, 0.5, {"PRO_SVC": 3, "OFF_SUP": 2, "FURN": 1, "MKT_SVC": 1, "IT_HW": 1}),
    ("Finance", "CORPORATE", 0.4, 0.8, {"PRO_SVC": 3, "SW_LIC": 2, "OFF_SUP": 2, "IT_HW": 1}),
    ("Human Resources", "CORPORATE", 0.4, 0.6, {"PRO_SVC": 2, "OFF_SUP": 2, "SW_LIC": 1, "FURN": 1, "MKT_SVC": 1}),
    ("Legal & Compliance", "CORPORATE", 0.3, 0.4, {"PRO_SVC": 4, "OFF_SUP": 1, "SW_LIC": 1}),
    ("Procurement", "CORPORATE", 0.3, 0.6, {"OFF_SUP": 2, "SW_LIC": 1, "PRO_SVC": 1, "LOG_SVC": 1}),
    ("IT Infrastructure", "TECHNOLOGY", 1.3, 1.0, {"IT_HW": 5, "SW_LIC": 3, "ELEC": 1, "PRO_SVC": 1}),
    ("Software Engineering", "TECHNOLOGY", 1.0, 1.6, {"SW_LIC": 4, "IT_HW": 3, "PRO_SVC": 2}),
    ("Research & Development", "TECHNOLOGY", 1.2, 1.2, {"LAB_EQ": 4, "ELEC": 2, "RAW_MAT": 1, "IT_HW": 1, "SW_LIC": 1, "SAFETY": 1}),
    ("Manufacturing", "OPERATIONS", 1.6, 2.0, {"RAW_MAT": 5, "MRO": 4, "PACK": 2, "ELEC": 2, "SAFETY": 2}),
    ("Quality Assurance", "OPERATIONS", 0.6, 0.7, {"LAB_EQ": 3, "SAFETY": 1, "SW_LIC": 1, "MRO": 1}),
    ("Logistics & Warehousing", "OPERATIONS", 1.0, 1.1, {"LOG_SVC": 4, "PACK": 3, "MRO": 1, "SAFETY": 1}),
    ("Facilities", "OPERATIONS", 1.0, 0.7, {"FAC_SVC": 4, "FURN": 2, "MRO": 2, "ELEC": 1, "SAFETY": 1}),
    ("Marketing", "COMMERCIAL", 0.9, 0.8, {"MKT_SVC": 5, "SW_LIC": 1, "OFF_SUP": 1, "PRO_SVC": 1}),
    ("Sales", "COMMERCIAL", 0.6, 1.3, {"MKT_SVC": 2, "IT_HW": 1, "OFF_SUP": 1, "SW_LIC": 1, "LOG_SVC": 1}),
    ("Customer Support", "COMMERCIAL", 0.4, 1.0, {"SW_LIC": 2, "IT_HW": 2, "OFF_SUP": 1, "FURN": 1}),
    ("Health, Safety & Environment", "OPERATIONS", 0.5, 0.4, {"SAFETY": 5, "PRO_SVC": 1, "LAB_EQ": 1, "FAC_SVC": 1}),
]

# code: (name, budget_type, is_service, import duty rate, standard lead days, supplier noun,
#        [(item name, uom, list price USD), ...])
CATEGORIES = {
    "IT_HW": ("IT Hardware", "CAPEX", False, 0.020, 10, "Technology Distribution", [
        ("Business Laptop 14in", "EA", 1150), ("Engineering Workstation", "EA", 2600),
        ("27in Monitor", "EA", 310), ("USB-C Docking Station", "EA", 220),
        ("48-Port Network Switch", "EA", 3400), ("Rack Server 2U", "EA", 9800),
        ("Wireless Access Point", "EA", 480), ("UPS 3kVA", "EA", 1900),
        ("Enterprise SSD 3.84TB", "EA", 720), ("Rugged Tablet", "EA", 1650)]),
    "SW_LIC": ("Software & SaaS Licences", "OPEX", True, 0.0, 3, "Software Solutions", [
        ("CAD Seat Licence (annual)", "LIC", 4200), ("Office Suite Subscription (annual)", "LIC", 264),
        ("Endpoint Security Licence (annual)", "LIC", 58), ("Database Enterprise Core Licence", "LIC", 7200),
        ("Project Management SaaS Seat (annual)", "LIC", 180), ("Analytics Platform Seat (annual)", "LIC", 1500),
        ("ERP Module User Licence", "LIC", 2100)]),
    "OFF_SUP": ("Office Supplies", "OPEX", False, 0.030, 4, "Office Supply", [
        ("Copy Paper A4 (box of 5 reams)", "BOX", 32), ("Printer Toner Cartridge", "EA", 145),
        ("Notebook & Stationery Kit", "EA", 18), ("Whiteboard Markers (pack of 12)", "PK", 14),
        ("Filing Folders (box of 100)", "BOX", 26), ("Desk Organiser Set", "EA", 35),
        ("Shipping Labels (roll)", "ROLL", 22)]),
    "FURN": ("Furniture & Fixtures", "CAPEX", False, 0.040, 21, "Furniture Works", [
        ("Ergonomic Task Chair", "EA", 420), ("Height-Adjustable Desk", "EA", 780),
        ("4-Drawer Filing Cabinet", "EA", 360), ("Conference Table 10-Seat", "EA", 2400),
        ("Acoustic Office Pod", "EA", 14500), ("Breakroom Table Set", "EA", 950),
        ("Storage Shelving Unit", "EA", 290)]),
    "LAB_EQ": ("Laboratory Equipment", "CAPEX", False, 0.035, 30, "Scientific Instruments", [
        ("Benchtop Centrifuge", "EA", 6800), ("Analytical Balance", "EA", 3900),
        ("Fume Hood 6ft", "EA", 18500), ("Digital Microscope", "EA", 5200),
        ("Laboratory Refrigerator", "EA", 4300), ("pH/Conductivity Meter", "EA", 1250),
        ("Environmental Test Chamber", "EA", 42000)]),
    "MRO": ("MRO & Spare Parts", "OPEX", False, 0.030, 7, "Industrial Supply", [
        ("Bearing Assembly", "EA", 85), ("Hydraulic Hose Kit", "EA", 140), ("Industrial V-Belt", "EA", 38),
        ("Lubricant Drum 200L", "EA", 620), ("Pneumatic Cylinder", "EA", 310),
        ("Replacement Motor 5HP", "EA", 1450), ("Conveyor Roller", "EA", 120), ("Pump Seal Kit", "EA", 260)]),
    "RAW_MAT": ("Raw Materials", "OPEX", False, 0.050, 14, "Materials", [
        ("Aluminium Sheet 6061", "KG", 6.8), ("Stainless Steel Bar 304", "KG", 5.4),
        ("Polypropylene Resin", "KG", 2.1), ("Copper Wire Rod", "KG", 10.2),
        ("Epoxy Resin Compound", "KG", 14.5), ("Carbon Steel Plate", "KG", 1.9)]),
    "PACK": ("Packaging Materials", "OPEX", False, 0.045, 10, "Packaging", [
        ("Corrugated Shipping Box (bundle of 25)", "PK", 48), ("Stretch Wrap Film Roll", "ROLL", 34),
        ("Wooden Pallet", "EA", 18), ("Foam Insert Set (pack of 50)", "PK", 95),
        ("Pallet Strapping Kit", "EA", 75), ("Custom Printed Carton (pack of 100)", "PK", 260)]),
    "ELEC": ("Electrical Components", "OPEX", False, 0.025, 12, "Electrical Components", [
        ("Industrial PLC Controller", "EA", 2400), ("Circuit Breaker 3-Pole", "EA", 190),
        ("Power Cable 4mm (100m reel)", "ROLL", 310), ("Variable Frequency Drive", "EA", 1850),
        ("LED High-Bay Fixture", "EA", 240), ("Proximity Sensor", "EA", 95), ("Terminal Block Set", "EA", 60)]),
    "SAFETY": ("Safety & PPE", "OPEX", False, 0.035, 6, "Safety Products", [
        ("Safety Helmet (box of 10)", "BOX", 180), ("Cut-Resistant Gloves (box of 12 pairs)", "BOX", 96),
        ("Safety Eyewear (box of 10)", "BOX", 75), ("High-Visibility Vest (box of 10)", "BOX", 110),
        ("N95 Respirator (box of 20)", "BOX", 52), ("Fall Arrest Harness", "EA", 240),
        ("Safety Footwear (pair)", "EA", 130), ("First Aid Station", "EA", 320)]),
    "PRO_SVC": ("Professional Services", "OPEX", True, 0.0, 10, "Consulting Group", [
        ("IT Consulting", "HR", 165), ("Management Consulting", "HR", 240), ("Legal Advisory", "HR", 320),
        ("Audit Support", "HR", 190), ("Engineering Contractor", "HR", 120), ("Data Science Consultant", "HR", 180)]),
    "MKT_SVC": ("Marketing & Print Services", "OPEX", True, 0.0, 14, "Creative Studio", [
        ("Trade Show Booth Package", "EA", 18500), ("Digital Campaign Management", "HR", 110),
        ("Brochure Printing (1000 units)", "EA", 950), ("Video Production Day", "EA", 3200),
        ("Market Research Study", "EA", 14000), ("Promotional Merchandise (pack of 100)", "PK", 680)]),
    "FAC_SVC": ("Facilities Services", "OPEX", True, 0.0, 7, "Facility Services", [
        ("Janitorial Services", "HR", 38), ("HVAC Maintenance Visit", "EA", 650),
        ("Security Guard Services", "HR", 42), ("Landscaping Visit", "EA", 480),
        ("Pest Control Visit", "EA", 220), ("Office Relocation Crew", "HR", 85)]),
    "LOG_SVC": ("Logistics & Freight Services", "OPEX", True, 0.0, 5, "Freight Logistics", [
        ("Full Truckload Shipment", "EA", 2100), ("LTL Pallet Shipment", "EA", 240),
        ("Express Courier Package", "EA", 45), ("Ocean Container 40ft", "EA", 4200),
        ("Warehouse Storage (pallet-month)", "EA", 28), ("Customs Brokerage Entry", "EA", 180)]),
}
GOODS_VARIANT = ("Premium", 1.4)   # each goods item also exists as a premium variant
UOMS = ("EA", "BOX", "PK", "KG", "ROLL", "LIC", "HR")

FIRST_NAMES = """Aarav Abigail Adrian Aisha Alejandro Amara Andre Anika Arjun Beatriz Caleb Camila
Chen Chloe Daniel Deepa Diego Elena Elijah Emeka Fatima Felix Grace Hannah Hiroshi Ibrahim Imani
Isabel Jamal Jasmine Javier Julia Kai Kavya Kenji Lara Leila Liam Lucia Malik Maria Mateo Maya
Mei Mohammed Nadia Naomi Nikhil Noah Olivia Omar Priya Rafael Rosa Samuel Sana Sofia Tariq
Valentina Wei Yara Yusuf Zara Zoe""".split()
LAST_NAMES = """Abbott Adeyemi Alvarez Anand Bauer Becker Bennett Bose Carter Castillo Chandra Chen
Costa Das Dimitrov Edwards Fischer Flores Fraser Garcia Gupta Haddad Hansen Ibarra Iyer Jansen
Kapoor Kim Kowalski Lambert Larsen Lee Lopez Mahmoud Martin Mehta Mendes Morales Murphy Nakamura
Nguyen Novak Okafor Olsen Patel Petrov Quinn Ramirez Reddy Rossi Santos Schmidt Shah Silva Singh
Suzuki Tanaka Thompson Vargas Walsh Weber Williams Yamamoto Zhang""".split()

SUPPLIER_PREFIXES = """Alder Amberline Apexfield Bluefield Birchwood Brightpath Cedarline Clearwater
Cobaltis Copperfield Crestway Driftwood Eastmere Evergreen Falconridge Fernbrook Granite Peak Harborview
Highland Ironbridge Juniper Keystone Lakeshore Larkspur Meridian Northgate Oakmont Orionis Pinecrest
Quarryside Redwood Riverstone Sablewood Silverline Stonehill Summit Ridge Tamarack Trident Tundra
Vertexa Westbrook Willowmere Zephyrine Ashgrove Bramblecote Coldwater Dunmore Elmstead Foxhollow
Glenmoor Hollowell Kestrel Lindenhall Marlowe Netherby Oakhurst Penrose Ravenscroft Thornbury
Wexford""".replace("Granite Peak", "Granite_Peak").replace("Summit Ridge", "Summit_Ridge").split()
COUNTRIES = [("US", "USD", 0.70), ("CA", "CAD", 0.07), ("MX", "MXN", 0.05), ("DE", "EUR", 0.06),
             ("GB", "GBP", 0.05), ("IN", "INR", 0.04), ("CN", "CNY", 0.03)]
COUNTRY_SUFFIX = {"US": ("Inc.", "LLC", "Corp."), "CA": ("Ltd.", "Inc."), "MX": ("S.A. de C.V.",),
                  "DE": ("GmbH", "AG"), "GB": ("Ltd", "PLC"), "IN": ("Pvt. Ltd.",), "CN": ("Co., Ltd.",)}
# Synthetic monthly FX starting points (USD per unit). Illustrative only - not market data.
FX_BASE = {"USD": 1.0, "EUR": 1.085, "GBP": 1.27, "CAD": 0.735, "MXN": 0.0565, "INR": 0.01195,
           "CNY": 0.1385}
CARRIERS = ("Northbound Freight", "BlueLine Courier", "Coastal Express", "Summit Haulage",
            "Supplier Own Fleet")

JUSTIFICATIONS = (
    "Replacement of end-of-life {item} for the {dept} team.",
    "Capacity expansion: additional {item} required for the approved {quarter} plan.",
    "Consumables replenishment ({item}) based on the rolling 90-day usage forecast.",
    "Required to start an approved {dept} project on schedule.",
    "Audit finding remediation: {item} needed to meet compliance requirements.",
    "Support for new hires joining {dept} this quarter ({item}).",
    "Preventive maintenance programme - {item} scheduled per asset plan.",
)

STAFF_TITLES = ("Analyst", "Specialist", "Coordinator", "Engineer", "Associate", "Technician")

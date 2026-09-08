# Product Vision (source: Restaurant Management.docx)

> Verbatim conversion of the original vision document. This is the *what we eventually want*, not the build order. Build order lives in `docs/plan/month-1.md`.

**Restaurant Management & Intelligence Platform --- Project Plan**

**1. Project Vision**

Build a **comprehensive restaurant management and intelligence
application** that connects the entire restaurant ecosystem---owners,
administrators, managers, chefs, kitchen staff, waiters, cleaners,
store/inventory staff and customers---into one platform.

The application should not merely record orders and inventory. It should
continuously collect operational, customer, staff, food, inventory,
communication and financial information and convert it into **actionable
insights for managers and owners**.

The ultimate goal is to help restaurants:

- Increase revenue and profitability

- Improve customer experience

- Reduce food and inventory wastage

- Avoid stock-outs and stale/expired raw materials

- Optimize their menu

- Improve kitchen and waiter performance

- Improve communication between departments

- Detect operational problems early

- Reduce unnecessary costs

- Make purchasing and staffing decisions using data

- Give owners visibility into the restaurant without needing to be
  physically present

------------------------------------------------------------------------

**2. User Roles**

The system should support role-based access.

**Owner**

Complete business visibility, analytics, financial performance, employee
performance, menu intelligence, inventory, incidents and alerts.

**Administrator**

System configuration, users, permissions, restaurant setup, master data
and audit controls.

**Restaurant Manager**

Daily operations, staff, inventory, customer complaints, kitchen/service
performance, incidents, procurement and tasks.

**Chef / Kitchen Manager**

Orders, KOTs, preparation status, recipes, ingredients, kitchen
performance, wastage and quality issues.

**Kitchen Staff**

Assigned preparation tasks, order status, ingredient availability and
operational communication.

**Waiter / Captain**

Table management, customer orders, customer requests, special
instructions, complaints and service status.

**Inventory / Store Manager**

Stock, receiving, transfers, wastage, expiry, purchase orders and
supplier management.

**Cleaner / Housekeeping**

Cleaning tasks, schedules, hygiene checklists and issue reporting.

**Accountant / Finance User**

Sales, expenses, invoices, payments, reconciliation and financial
reports.

**Customer**

Menu, ordering, feedback, ratings, complaints, requests and loyalty
features.

------------------------------------------------------------------------

**3. Restaurant Dashboard**

The home dashboard should provide an immediate picture of the
restaurant.

**Today\'s overview**

- Sales

- Number of orders

- Number of customers/covers

- Average order value

- Tables occupied/free

- Open orders

- Kitchen delays

- Customer complaints

- Staff attendance

- Inventory alerts

- Food wastage

- Expenses

- Estimated profit

**Restaurant Health Score**

The system can produce an overall score based on:

**Sales + Customer Experience + Kitchen + Service + Inventory + Staff +
Cost + Wastage**

The manager should immediately see what requires attention rather than
navigating through dozens of screens.

------------------------------------------------------------------------

**4. POS & Order Management**

The application should support the restaurant\'s complete order
lifecycle.

**Features**

- Dine-in orders

- Takeaway

- Delivery

- Table assignment

- QR ordering

- Waiter ordering

- Order modification

- Special instructions

- Allergens/preferences

- Discounts

- Taxes

- Split bills

- Multiple payment methods

- Refunds

- Cancellations

- Order history

- Customer association

Orders should automatically flow to the relevant kitchen station.

------------------------------------------------------------------------

**5. Kitchen / KOT Management**

The chef should have a live kitchen dashboard.

**Features**

- Incoming orders

- KOT generation

- Order priority

- Station assignment

- Preparation status

- Ready status

- Delay alerts

- Cancelled items

- Remake requests

- Special instructions

- Preparation time tracking

- Kitchen workload

- Chef/team performance

The system should identify bottlenecks.

For example:

Average preparation time increased 19% between 8--9 PM.

This should automatically become a management insight.

------------------------------------------------------------------------

**6. Menu & Dish Intelligence**

This should be one of the core differentiating modules.

The application should track every dish\'s:

- Orders

- Daily demand

- Weekly demand

- Monthly demand

- Customer rating

- Repeat orders

- Complaints

- Returns

- Cancellation rate

- Preparation time

- Food cost

- Selling price

- Gross margin

- Ingredient usage

- Wastage

- Popularity by day/time

- Popularity by customer segment

The system should classify dishes into categories such as:

**Customer Favorites**\
High demand + high ratings

**Profit Makers**\
High/healthy margin

**Slow Movers**\
Low demand

**Waste Generators**\
Low demand + high wastage

**Problem Dishes**\
High demand but poor ratings/complaints

**Hidden Gems**\
High ratings but low awareness/orders

------------------------------------------------------------------------

**7. Ingredient & Recipe Management**

Every dish should be connected to a standardized recipe.

Example:

**Butter Chicken**

Chicken --- 250g\
Cream --- 40ml\
Tomato --- 100g\
Butter --- 20g\
Spices --- X grams

This creates a relationship:

**Dish → Recipe → Ingredients → Inventory → Cost → Profit**

Whenever a dish is sold, the system can estimate ingredient consumption.

------------------------------------------------------------------------

**8. Inventory Management**

Inventory should operate at raw-material level.

**Track**

- Current stock

- Minimum stock level

- Maximum stock level

- Safety stock

- Units

- Batch

- Expiry date

- Purchase price

- Supplier

- Storage location

- Incoming stock

- Transferred stock

- Wasted stock

- Consumed stock

- Adjustments

**Alerts**

- Low stock

- Overstock

- Near expiry

- Expired material

- Unusual consumption

- Unexpected wastage

- Stock discrepancy

------------------------------------------------------------------------

**9. Monthly Raw Material Planning**

This is one of the most valuable management features.

The manager can enter:

- Expected orders/covers

- Expected growth

- Seasonal demand

- Events

- Special promotions

- Target inventory

- Safety-stock percentage

- Monthly procurement budget

The system calculates:

**Forecast Demand → Ingredient Requirement → Existing Stock → Incoming
Stock → Safety Stock → Purchase Requirement**

For example:

Chicken required this month: 280 kg\
Current stock: 42 kg\
Incoming: 30 kg\
Safety stock: 27 kg\
**Recommended purchase: 235 kg**

The manager can accept, edit or reject the recommendation.

------------------------------------------------------------------------

**10. Shelf-Life & Freshness Management**

This is essential for preventing stale food.

The system should know the shelf life of every ingredient.

Instead of simply saying:

\"You need 180 kg tomatoes this month\"

it should potentially recommend:

\"Purchase 40 kg weekly because expected consumption and shelf life make
a monthly bulk purchase inefficient.\"

The system should also use:

**FEFO --- First Expiry, First Out**

so ingredients that expire first are consumed first.

------------------------------------------------------------------------

**11. Menu Optimization**

The system should identify **ingredient overlap**.

For example:

10 different dishes may use the same:

- Paneer

- Onion

- Tomato

- Capsicum

- Cream

- Spices

The application should tell the owner:

\"These 14 dishes use only 8 additional ingredients and generate 28% of
menu revenue.\"

This allows restaurants to potentially offer a broad menu without
maintaining unnecessarily large and expensive inventories.

------------------------------------------------------------------------

**12. Menu Engineering**

For each dish, calculate:

**Popularity × Profitability × Rating × Operational Complexity**

This creates recommendations such as:

Keep\
Promote\
Reprice\
Modify\
Reduce preparation\
Remove from menu\
Introduce similar dish

The system should also identify dishes that look popular but generate
poor margins.

------------------------------------------------------------------------

**13. Procurement & Supplier Management**

The application should support:

- Supplier database

- Purchase orders

- Quotations

- Purchase history

- Supplier prices

- Delivery times

- Quality ratings

- Partial deliveries

- Invoice records

- Payment status

- Supplier reliability

The system should compare historical supplier pricing.

For example:

Supplier A: ₹92/kg\
Supplier B: ₹86/kg\
Supplier B delivery reliability: 82%

The manager/owner can make an informed decision rather than choosing
purely based on price.

------------------------------------------------------------------------

**14. Food Wastage Management**

Every wastage event should have a reason.

Examples:

- Expired

- Over-preparation

- Burnt

- Incorrect order

- Customer return

- Spoilage

- Storage issue

- Preparation error

The application should calculate:

**Quantity wasted + Cost wasted + Reason + Department + Employee/shift +
Dish**

Then produce insights.

42% of wastage this week came from over-preparation between 2--5 PM.

------------------------------------------------------------------------

**15. Waiter & Service Performance**

The platform should measure service objectively.

Track:

- Tables served

- Orders handled

- Order accuracy

- Average service time

- Customer ratings

- Complaints

- Compliments

- Upselling

- Table turnover

- Tips

- Attendance

- Shift performance

It should not be purely a \"rating employees\" system. Managers should
see **why** a score is good or poor.

------------------------------------------------------------------------

**16. Chef & Kitchen Performance**

Track:

- Orders prepared

- Average preparation time

- Delayed orders

- Remakes

- Food-quality complaints

- Wastage

- Order accuracy

- Station workload

- Customer ratings

- Hygiene checklist

- Shift performance

This allows management to distinguish between:

**individual performance problems** and **systemic kitchen problems**.

------------------------------------------------------------------------

**17. Staff Attendance & Shift Management**

Add:

- Attendance

- Shifts

- Leave

- Overtime

- Late arrivals

- Shift swaps

- Staff availability

- Staffing requirements

The application should eventually forecast:

Friday 8--10 PM expected demand is 30% higher than normal.\
Recommended staffing: 2 additional service staff + 1 kitchen staff.

------------------------------------------------------------------------

**18. Customer Feedback & Experience**

Customers should be able to provide:

- Dish rating

- Restaurant rating

- Service rating

- Waiter rating

- Food quality

- Cleanliness rating

- Feedback

- Complaint

- Suggestions

The application should connect feedback to actual operational data.

For example:

Customer ratings dropped during 8--10 PM.

The platform can investigate whether:

- Wait times increased

- Kitchen delays increased

- Staffing was insufficient

- Certain dishes caused problems

------------------------------------------------------------------------

**19. Communication System**

Create an internal communication platform specifically for restaurant
operations.

Communication between:

**Chef ↔ Waiter**\
**Waiter ↔ Manager**\
**Chef ↔ Manager**\
**Cleaner ↔ Manager**\
**Inventory ↔ Kitchen**\
**Manager ↔ Owner**

Messages should support:

- Text

- Photos

- Video

- Voice notes

- Documents

- Mentions

- Priority

- Read status

- Acknowledgement

**20. Task Management**

Messages should optionally become tasks.

Example:

\"Chicken stock is low.\"

Manager:

**Create Task → Purchase Chicken → Assign Store Manager → Due by 6 PM**

Track:

**Created → Assigned → Accepted → In Progress → Completed → Verified**

This prevents issues from disappearing inside chat.

------------------------------------------------------------------------

**21. Incident Management**

Any employee should be able to report an incident.

Examples:

- Customer complaint

- Food-quality problem

- Equipment failure

- Missing inventory

- Hygiene issue

- Staff conflict

- Order mistake

- Safety incident

- Supplier issue

- Payment problem

Each incident should contain:

- Date/time

- Location

- People involved

- Description

- Photos/video

- Related order

- Related table

- Related dish

- Severity

- Assigned person

- Resolution

- Manager comments

- Final status

------------------------------------------------------------------------

**22. Evidence & Video**

Video/photo attachment should be configurable.

Some restaurants may want it; others may not.

The system should support:

**Uploaded video**

Staff can attach a recording directly to an incident.

**CCTV integration --- optional**

Where technically supported and legally appropriate, a restaurant can
integrate selected cameras.

If an incident occurred at:

**9:17 PM**

the incident record could provide:

**9:12--9:22 PM footage**

rather than forcing the owner to search hours of footage manually.

Video retention should be configurable.

------------------------------------------------------------------------

**23. Permissions & Privacy**

This needs to be designed from day one.

Different users should see different data.

For example:

**Waiter**\
→ Their orders/tasks/communications

**Chef**\
→ Kitchen information

**Manager**\
→ Restaurant operational information

**Owner**\
→ Full business analytics

**Administrator**\
→ Configuration and permissions

Sensitive information should be protected through:

- Role-based access

- Audit logs

- Login security

- Session management

- Data encryption

- Configurable retention

- Access history

- Video permissions

- Communication permissions

------------------------------------------------------------------------

**24. Owner Dashboard**

The owner should be able to understand the restaurant without going
through operational details.

**Business**

- Revenue

- Profit

- Expenses

- Food cost

- Labour cost

- Average order value

- Sales trends

**Operations**

- Customer rating

- Kitchen performance

- Service performance

- Wastage

- Inventory

- Complaints

**People**

- Staff performance

- Attendance

- Productivity

- Overtime

**Menu**

- Best sellers

- Worst sellers

- Most profitable

- Least profitable

- Customer favorites

**Procurement**

- Spend

- Supplier performance

- Upcoming purchases

- Cost changes

**25. Smart Escalation**

The system shouldn\'t alert everybody about everything.

Example:

**Minor issue**

1 waiter makes an order mistake

→ Captain/Manager

**Repeated issue**

8 mistakes in one day

→ Manager

**Serious pattern**

Order accuracy drops 15% for one week

→ Manager + Owner

**Critical issue**

Major customer complaint / safety incident

→ Immediate escalation

This will prevent notification overload.

------------------------------------------------------------------------

**26. AI Restaurant Advisor**

This should sit on top of the entire platform.

The AI should analyze:

**Sales + Orders + Customers + Menu + Recipes + Inventory +
Procurement + Wastage + Staff + Kitchen + Communication + Incidents**

and answer:

**\"What is happening in my restaurant and what should I do?\"**

Example:

Customer complaints regarding Biryani increased 24% this week.
Preparation time also increased 18%, primarily between 8--10 PM. Three
service employees reported delays during the same period.

**Likely issue:** kitchen capacity during peak hours.

**Suggested actions:** review kitchen staffing and preparation schedule.

------------------------------------------------------------------------

**27. Predictive Analytics**

Later versions can forecast:

**Demand**

Predict:

- Tomorrow\'s orders

- Weekly demand

- Monthly demand

- Dish-level demand

**Inventory**

Predict:

- When stock will run out

- How much to buy

- When to purchase

**Staffing**

Predict:

- Required staff by shift

- Peak periods

**Customer**

Predict:

- Repeat customers

- Churn risk

- Customer preferences

**Waste**

Predict:

- Likely wastage

- Ingredients likely to expire

------------------------------------------------------------------------

**28. Alerts & Notifications**

Examples:

🔴 Critical incident\
🟠 Stock shortage\
🟡 Ingredient approaching expiry\
🟡 Customer rating falling\
🔵 Supplier price increase\
🟢 Purchase order received

Notifications should work through configurable in-app/push channels, and
potentially email/SMS/WhatsApp where integrations are available.

------------------------------------------------------------------------

**29. Reports**

The system should provide:

- Daily report

- Weekly report

- Monthly report

- Sales report

- Profitability report

- Inventory report

- Wastage report

- Staff report

- Customer report

- Menu report

- Procurement report

- Incident report

- Supplier report

The owner should be able to export relevant reports.

**30. Audit Trail**

Every important activity should be traceable.

For example:

Who changed the price of Paneer?\
Who changed the recipe?\
Who adjusted stock?\
Who cancelled the order?\
Who closed the incident?\
Who modified the purchase order?

This is extremely important for accountability and preventing internal
leakage/fraud.

------------------------------------------------------------------------

**31. Multi-Branch Support**

The architecture should ideally support multiple restaurants/branches.

Owner could eventually see:

**Branch A**\
Revenue ₹X

**Branch B**\
Revenue ₹Y

**Branch C**\
Revenue ₹Z

and compare:

- Sales

- Profit

- Staff

- Food cost

- Wastage

- Menu

- Inventory

------------------------------------------------------------------------

**32. Integrations**

The architecture should allow future integration with:

- Existing POS

- Payment systems

- Accounting software

- Delivery platforms

- QR ordering

- Printers

- Kitchen display systems

- Barcode scanners

- Weighing scales

- CCTV systems

- Supplier systems

The first version doesn\'t need every integration, but the backend
should not prevent them later.

------------------------------------------------------------------------

**33. Mobile + Web**

I\'d recommend:

**Mobile app**

For:

- Waiters

- Chefs

- Kitchen

- Cleaners

- Inventory staff

- Managers

**Web dashboard**

For:

- Owners

- Administrators

- Managers

- Analytics

- Reports

- Configuration

This makes much more sense than forcing everyone onto one interface.

------------------------------------------------------------------------

**34. MVP --- What We Should Build First**

I would **not** build everything at once.

**Phase 1 --- Core Restaurant Operations**

Build:

**Users & Roles**\
**Restaurant Setup**\
**Tables**\
**Menu**\
**Orders/POS**\
**KOT/Kitchen**\
**Waiter interface**\
**Inventory**\
**Basic recipes**\
**Customer feedback**\
**Communication**\
**Tasks**\
**Basic manager dashboard**

**Phase 2 --- Intelligence**

Add:

**Dish analytics**\
**Food-cost calculation**\
**Wastage**\
**Procurement**\
**Monthly raw-material planning**\
**Supplier management**\
**Staff performance**\
**Advanced reports**

**Phase 3 --- AI**

Add:

**Demand forecasting**\
**Inventory forecasting**\
**Menu optimization**\
**AI insights**\
**AI restaurant advisor**\
**Natural-language analytics**

For example:

\"Why did profit fall this month?\"

The system should investigate the underlying data and explain it.

**Phase 4 --- Advanced Operations**

Add:

**CCTV integration**\
**Video incident retrieval**\
**Multi-branch management**\
**Advanced predictive staffing**\
**Automated procurement**\
**External integrations**

------------------------------------------------------------------------

**35. The Core Data Model**

At the center of the application, the relationships should look roughly
like:

RESTAURANT

│

├── USERS / STAFF

│

├── TABLES

│

├── CUSTOMERS

│

├── MENU

│ │

│ └── RECIPES

│ │

│ └── INGREDIENTS

│

├── ORDERS

│ │

│ └── KOT

│

├── INVENTORY

│

├── SUPPLIERS

│

├── PURCHASE ORDERS

│

├── WASTAGE

│

├── STAFF PERFORMANCE

│

├── CUSTOMER FEEDBACK

│

├── COMMUNICATION

│

├── TASKS

│

├── INCIDENTS

│ │

│ └── PHOTO / VIDEO / CCTV

│

└── FINANCIAL DATA

Then the analytics/AI layer sits above all of these.

------------------------------------------------------------------------

**36. The Ultimate Product**

The final product should answer four questions continuously:

**What happened?**

Reporting and historical data.

**What is happening?**

Real-time restaurant operations.

**What is going to happen?**

Forecasting and predictive analytics.

**What should I do?**

AI-powered recommendations.

That gives you a product much more ambitious and differentiated than a
basic restaurant POS.

**Product positioning**

**\"An intelligent operating system for restaurants that connects
people, food, inventory, customers and finances---and turns restaurant
data into actions.\"**

The most important architectural principle I\'d carry into development
is this:

**Everything should be connected.**

A customer complaint shouldn\'t be an isolated complaint. It should be
connectable to the **dish → order → waiter → kitchen → preparation time
→ ingredient → inventory → wastage → cost → incident → resolution**.

That connected data is what ultimately makes the AI and management
intelligence genuinely useful.

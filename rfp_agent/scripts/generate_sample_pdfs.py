"""Generate fictional supplier RFP responses (no real data) into sample_rfps/.

Usage: python scripts/generate_sample_pdfs.py      (needs reportlab)
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).resolve().parent.parent / "sample_rfps"
OUT.mkdir(exist_ok=True)
REQ = ("RFP-2026-017: Enterprise Vendor Management and Spend Analytics Platform "
       "(500 users, SAP S/4HANA + Oracle Fusion Finance + Okta SSO integration)")

ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=17, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=8, spaceAfter=3)
BODY = ParagraphStyle("b", parent=ss["Normal"], fontSize=10.5, leading=15)
SMALL = ParagraphStyle("s", parent=ss["Normal"], fontSize=8, textColor=colors.grey)

PROFILES = {
 "Apex Systems": "Apex Systems is an enterprise software vendor headquartered in Frankfurt with 650 employees and a focus on regulated industries such as banking and manufacturing. Its engineering organisation owns the entire product stack, and the company invests heavily in security assurance and platform reliability.",
 "BrightPath Tech": "BrightPath Tech is a start-up founded in 2022 with 35 employees. It builds lightweight SaaS tools for small and mid-sized organisations and competes primarily on speed of delivery and low cost.",
 "NexaWorks": "NexaWorks is a mid-sized software company with 320 employees and offices in Toronto and Dublin. It combines a modular product with a professional services and customer success organisation, and is known for predictable, well-governed delivery.",
 "Orbit Digital": "Orbit Digital was founded in 2008 and has 210 employees. It is a specialist in procurement technology and services with a large installed base and many long-standing enterprise customers in manufacturing and the public sector.",
}

SUPPLIERS = {
"Apex_Systems_RFP": dict(name="Apex Systems", sections=[
 ("1. Executive Summary", [
  "Apex Systems understands that the procurement organisation needs a single platform to manage vendor onboarding, contracts, performance and spend analytics for 500 users across four regions. We propose our Apex VendorCore platform, a cloud-native product that is already in production at large manufacturers and banks.",
  "Our proposal emphasises engineering depth, security assurance and long-term scalability. We are not the cheapest bidder; our price reflects a premium architecture and a full compliance programme."]),
 ("2. Proposed Solution and Technical Architecture", [
  "VendorCore is built as a set of microservices on Kubernetes with REST and GraphQL APIs. The platform auto-scales horizontally and was load tested at 5,000 concurrent users, ten times the requirement. Multi-region active-passive deployment provides disaster recovery with a 15-minute RPO and 1-hour RTO; contractual uptime SLA is 99.95%.",
  "Integration: we provide a SAP-certified S/4HANA connector, an Oracle Fusion Finance adapter delivered through Oracle Integration Cloud, and SSO through SAML 2.0 and OIDC with Okta. Event streaming (Kafka) supports near-real-time spend synchronisation. An architecture diagram and integration specification are included in Appendix A."]),
 ("3. Implementation Approach, Timeline and Team", [
  "Delivery follows five phases over 9 months: Discovery (weeks 1-4), Design (5-10), Build and Integrate (11-26), UAT and Hardening (27-33), Go-live and Hypercare (34-39). The core team has 12 named roles including a project manager, solution architect, two integration engineers and a security lead.",
  "A risk register is maintained weekly; top risks are ERP data quality and SSO policy changes, mitigated through early data profiling. The schedule is longer than some competitors because we complete full penetration testing before go-live."]),
 ("4. Price Table (3-year, USD)", [
  ("TABLE", [["Item", "Year 1", "Year 2", "Year 3"],
            ["Platform licence (500 users)", "420,000", "420,000", "420,000"],
            ["Implementation services", "310,000", "-", "-"],
            ["Integration (SAP, Oracle, Okta)", "120,000", "-", "-"],
            ["Premium support", "60,000", "60,000", "60,000"],
            ["Total 3-year cost", "910,000", "480,000", "480,000"]]),
  "Assumptions: fixed price for implementation; licence fees indexed at 3% after year 1; travel at cost; data migration of up to 5 million records included. Grand total: USD 1,870,000."]),
 ("5. Security, Compliance and Risk Controls", [
  "Apex holds ISO 27001 and SOC 2 Type II certifications, audited annually. Data is encrypted with AES-256 at rest and TLS 1.3 in transit, with field-level encryption for bank details. Role-based access control and mandatory MFA are enforced; all administrative actions are written to immutable audit logs retained for 7 years and streamed to the customer's SIEM.",
  "A third-party penetration test is performed twice a year and results are shared under NDA. We sign a GDPR data processing agreement and support EU data residency."]),
 ("6. Support Model, Experience and References", [
  "Standard support is business hours (8x5) with a 4-hour P1 response; 24x7 premium support is priced in the table above. We have delivered 6 similar vendor-management deployments in the last four years.",
  "References: a European automotive group (8,000 users) and a regional bank (2,500 users); contact details provided on request."]),
]),

"BrightPath_Tech_RFP": dict(name="BrightPath Tech", sections=[
 ("1. Executive Summary", [
  "BrightPath Tech offers the fastest and most affordable route to a vendor management platform. Our BrightVendor SaaS is simple, quick to roll out and priced to fit tight budgets. We can be live in 4 months.",
  "We are a young company and focus on a lean delivery model."]),
 ("2. Proposed Solution", [
  "BrightVendor is a multi-tenant SaaS application with standard dashboards for vendor records, contracts and spend. Integration with SAP is supported through scheduled CSV file import; a native API connector is planned for a later release. Oracle Fusion integration is to be defined with the customer. Single sign-on via SAML is available, OIDC is not yet supported.",
  "The platform runs on a single cloud region. Capacity for 500 users is expected to be sufficient; formal load test results are not yet available."]),
 ("3. Implementation Plan", [
  "Implementation takes 4 months in three phases: Setup (month 1), Configuration (months 2-3), Go-live (month 4). The team consists of 6 people including one project manager. Detailed milestones will be agreed after contract signature. Risk management is handled by the project manager on a best effort basis."]),
 ("4. Price Table (3-year, USD)", [
  ("TABLE", [["Item", "Year 1", "Year 2", "Year 3"],
            ["Subscription (500 users)", "190,000", "190,000", "190,000"],
            ["Onboarding", "60,000", "-", "-"],
            ["Support", "included", "included", "included"],
            ["Total", "250,000", "190,000", "190,000"]]),
  "Assumptions: data migration is excluded; custom integrations are excluded and quoted separately. Grand total: USD 630,000."]),
 ("5. Security and Compliance", [
  "We follow industry-standard security practices and encrypt data at rest. ISO 27001 certification is in progress and expected next year. SOC 2 is not yet available. Details of audit logging are to be confirmed. We will comply with applicable privacy laws and can discuss a data processing agreement on request."]),
 ("6. Support and Experience", [
  "Support is by email, 9am-5pm on weekdays, with a response by the next business day. The company was founded in 2022 and has completed 2 similar projects. One reference customer (a regional retailer) is available on request."]),
]),

"NexaWorks_RFP": dict(name="NexaWorks", sections=[
 ("1. Executive Summary", [
  "NexaWorks proposes its NexaSource platform, a modular vendor management and spend analytics suite. Our approach balances capability, cost and delivery certainty, and is backed by a mature delivery methodology and a dedicated customer success organisation.",
  "We have studied the RFP requirements for SAP S/4HANA, Oracle Fusion Finance and Okta integration and have planned delivery around them."]),
 ("2. Proposed Solution and Architecture", [
  "NexaSource is a modular SaaS platform with a documented REST API. Pre-built connectors exist for SAP S/4HANA and Oracle Fusion Finance, and SSO is supported with SAML and OIDC for Okta. The platform auto-scales and has been load tested at 1,500 concurrent users, with a 99.9% uptime SLA and daily cross-region backups."]),
 ("3. Implementation Plan, Timeline and Team", [
  "Delivery takes 6 months in six phases with a week-level plan: Mobilise (weeks 1-2), Design (3-6), Build (7-16), Integrate (17-20), UAT with parallel run (21-24), Cutover and 90-day hypercare. A 14-person team is named with a RACI matrix covering the project manager, solution architect, data lead, integration leads, QA lead and change manager.",
  "A risk register with 10 identified risks and mitigations (data quality, scope creep, stakeholder availability, ERP release freezes) is reviewed weekly. Every milestone has acceptance criteria and a sign-off owner. Training covers administrators, buyers and approvers."]),
 ("4. Price Table (3-year, USD)", [
  ("TABLE", [["Item", "Year 1", "Year 2", "Year 3"],
            ["Platform licence (500 users)", "300,000", "300,000", "300,000"],
            ["Implementation and integration", "240,000", "-", "-"],
            ["24x7 support and customer success", "55,000", "55,000", "55,000"],
            ["Total", "595,000", "355,000", "355,000"]]),
  "Assumptions: fixed-price implementation; licence fixed for 3 years; data migration up to 3 million records included; no hidden fees. Grand total: USD 1,305,000."]),
 ("5. Security and Compliance", [
  "NexaWorks is ISO 27001 certified and holds a SOC 2 Type II report. Data is encrypted at rest and in transit, access is role-based with MFA, and audit trails are retained for 5 years. Annual third-party penetration testing is performed. A GDPR data processing agreement is provided."]),
 ("6. Support Model, Experience and References", [
  "Follow-the-sun 24x7 support with a 1-hour P1 response time and a named customer success manager (CSM) for the account. We have delivered 5 similar projects in the last three years and a structured training programme with quarterly reviews.",
  "References: four customers available (manufacturing, healthcare, logistics, and retail) with case studies attached."]),
]),

"Orbit_Digital_RFP": dict(name="Orbit Digital", sections=[
 ("1. Executive Summary", [
  "Orbit Digital has 18 years of experience delivering procurement technology and has completed more than 40 deployments for enterprise customers. We propose our OrbitSource platform together with our experienced services team.",
  "Our strength is delivery experience and customer relationships; many of our clients have been with us for over a decade."]),
 ("2. Proposed Solution", [
  "OrbitSource is a web-based vendor management platform covering onboarding, contracts, scorecards and spend dashboards. We will integrate with the client's ERP landscape using our flexible integration framework. The specific connectors and effort will be defined during the discovery phase. SSO will be supported using the client's identity provider.",
  "The platform scales as required for the user volume of this project."]),
 ("3. Implementation Plan", [
  "The project runs for approximately 7 months. Phases are Discovery, Build, Test and Go-live; the detailed plan will be finalised after discovery. The team will be staffed from our delivery pool and a project manager will be assigned. Risks will be tracked in a standard log."]),
 ("4. Price Table (3-year, USD)", [
  ("TABLE", [["Item", "Year 1", "Year 2", "Year 3"],
            ["Platform licence (500 users)", "330,000", "330,000", "330,000"],
            ["Implementation services", "190,000", "-", "-"],
            ["Integration work", "time and materials, estimate TBD", "-", "-"],
            ["Support", "45,000", "45,000", "45,000"]]),
  "Assumptions: integration effort will be billed on time and materials; indicative total USD 1,250,000 excluding integration."]),
 ("5. Security and Compliance", [
  "Orbit Digital is ISO 27001 certified and GDPR compliant. Data is encrypted in transit and at rest. A SOC 2 Type I report is available; Type II is planned for next year. Audit logging is provided at application level."]),
 ("6. Support Model, Experience and References", [
  "Support is available 8x5, with 24x7 cover for P1 incidents and a 2-hour P1 response. Over 18 years we have completed more than 40 similar deployments across industries, with long-standing client relationships.",
  "References: six named reference customers, with case studies and contact details in Appendix C, including two global manufacturers and a public-sector agency. Customer satisfaction has averaged 4.6/5 over the last five years."]),
]),
}


def build(filename: str, data: dict):
    doc = SimpleDocTemplate(str(OUT / f"{filename}.pdf"), pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=1.8*cm, bottomMargin=1.8*cm, title=f"{data['name']} - RFP Response")
    COVER = ParagraphStyle("cv", parent=ss["Title"], fontSize=26, leading=32, spaceAfter=10)
    story = [Spacer(1, 4*cm), Paragraph(data["name"], COVER),
             Paragraph("Response to Request for Proposal", H1), Spacer(1, 6), Paragraph(REQ, BODY),
             Spacer(1, 14), Paragraph("Submitted by: " + data["name"] + " (fictional supplier for classroom use)", BODY),
             Paragraph("Validity of offer: 90 days from submission.", BODY), Spacer(1, 14),
             Paragraph("Company Profile", H2), Paragraph(data["profile"], BODY), PageBreak()]
    for title, blocks in data["sections"]:
        story.append(Paragraph(title, H2))
        for b in blocks:
            if isinstance(b, tuple):
                t = Table(b[1], hAlign="LEFT")
                t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                                       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7")),
                                       ("FONTSIZE", (0, 0), (-1, -1), 9.5), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
                story += [t, Spacer(1, 4)]
            else:
                story += [Paragraph(b, BODY), Spacer(1, 6)]
    doc.build(story)


if __name__ == "__main__":
    for fn, d in SUPPLIERS.items():
        d["profile"] = PROFILES[d["name"]]
        build(fn, d)
    # Edge case for the validation demo: a PDF with no extractable text
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(OUT / "EDGE_blank_scanned_RFP.pdf"), pagesize=A4)
    c.rect(100, 400, 200, 100)  # only a drawn shape, no text
    c.save()
    print("Generated:", ", ".join(sorted(p.name for p in OUT.glob("*.pdf"))))

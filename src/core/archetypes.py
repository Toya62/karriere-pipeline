"""Domain Archetype Catalog for multi-tenant and multi-discipline job filtering.

Provides default target titles, search queries, and domain relevance keywords
for various engineering disciplines so non-CS candidates are never contaminated
by hardcoded Data Engineering / CS rules.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DomainArchetype:
    slug: str
    name: str
    description: str
    target_titles: list[str] = field(default_factory=list)
    relevance_keywords: list[str] = field(default_factory=list)
    domain_queries: list[str] = field(default_factory=list)
    forbidden_noise: list[str] = field(default_factory=list)


ARCHETYPE_CATALOG: dict[str, DomainArchetype] = {
    "civil_engineering": DomainArchetype(
        slug="civil_engineering",
        name="Civil Engineering (Bauingenieurwesen)",
        description="Structural design, construction management, geotechnical, and civil infrastructure.",
        target_titles=[
            "Bauingenieur",
            "Civil Engineer",
            "Tragwerksplaner",
            "Statiker",
            "Bauleiter",
            "Projektingenieur Bau",
            "Konstrukteur Ingenieurbau",
            "Planungsingenieur Tiefbau",
            "Geotechniker",
        ],
        relevance_keywords=[
            "Statik",
            "Tragwerksplanung",
            "Massivbau",
            "Stahlbau",
            "Holzbau",
            "AutoCAD",
            "Revit",
            "BIM",
            "HOAI",
            "VOB",
            "Eurocode",
            "Tiefbau",
            "Hochbau",
            "Geotechnik",
            "Bauüberwachung",
        ],
        domain_queries=[
            "Bauingenieur OR Civil Engineer",
            "Tragwerksplaner OR Statiker",
            "Bauleiter OR Projektingenieur Bau",
        ],
        forbidden_noise=[
            "maler",
            "lackierer",
            "dachdecker",
            "gerüstbauer",
        ],
    ),
    "mechanical_engineering": DomainArchetype(
        slug="mechanical_engineering",
        name="Mechanical Engineering (Maschinenbau)",
        description="Machine design, CAD modeling, thermodynamics, robotics, and production technology.",
        target_titles=[
            "Maschinenbauingenieur",
            "Mechanical Engineer",
            "Konstrukteur",
            "Entwicklungsingenieur Mechanik",
            "Berechnungsingenieur FEM",
            "Projektingenieur Maschinenbau",
            "CAD Konstrukteur",
        ],
        relevance_keywords=[
            "CAD",
            "SolidWorks",
            "CATIA",
            "Siemens NX",
            "Inventor",
            "FEM",
            "Ansys",
            "Thermodynamik",
            "Strömungsmechanik",
            "Getriebe",
            "Fertigungstechnik",
            "Automatisierung",
        ],
        domain_queries=[
            "Maschinenbauingenieur OR Mechanical Engineer",
            "Konstrukteur OR CAD",
            "Entwicklungsingenieur Mechanik",
        ],
        forbidden_noise=[
            "schweißer",
            "zerspanungsmechaniker",
            "cnc-bediener",
        ],
    ),
    "electrical_engineering": DomainArchetype(
        slug="electrical_engineering",
        name="Electrical Engineering (Elektrotechnik)",
        description="Hardware design, power electronics, embedded systems, PCB layout, and signal processing.",
        target_titles=[
            "Elektroingenieur",
            "Electrical Engineer",
            "Hardwareentwickler",
            "Embedded Systems Engineer",
            "Planungsingenieur Elektrotechnik",
            "Automatisierungsingenieur",
            "SPS Programmierer",
        ],
        relevance_keywords=[
            "Elektrotechnik",
            "Schaltplan",
            "PCB",
            "Altium",
            "KiCad",
            "SPS",
            "Siemens S7",
            "TIA Portal",
            "Leistungselektronik",
            "Messtechnik",
            "CAN Bus",
            "Mikrocontroller",
            "VDE",
        ],
        domain_queries=[
            "Elektroingenieur OR Electrical Engineer",
            "Hardwareentwickler OR Embedded",
            "Automatisierungsingenieur OR SPS",
        ],
        forbidden_noise=[
            "elektroinstallateur",
            "elektriker handwerk",
        ],
    ),
    "data_engineering": DomainArchetype(
        slug="data_engineering",
        name="Data Engineering & Analytics Platform",
        description="Data pipelines, ETL/ELT workflows, stream processing, lakehouse infrastructure, and cloud data platforms.",
        target_titles=[
            "Data Engineer",
            "Junior Data Engineer",
            "Big Data Engineer",
            "Data Platform Engineer",
            "ETL Developer",
            "Data Pipeline Developer",
            "Analytics Engineer",
        ],
        relevance_keywords=[
            "Python",
            "SQL",
            "ETL",
            "Kafka",
            "Apache Flink",
            "PyFlink",
            "Spark",
            "Airflow",
            "PostgreSQL",
            "AWS",
            "Docker",
            "Data Warehouse",
        ],
        domain_queries=[
            "Data Engineer OR Junior Data Engineer",
            "Data Platform Engineer OR ETL Developer",
            "PyFlink OR Kafka Engineer",
        ],
        forbidden_noise=[
            "data entry",
            "daten erfassung",
            "telemarketing",
        ],
    ),
    "backend_platform": DomainArchetype(
        slug="backend_platform",
        name="Backend & Platform Software Engineering",
        description="Server-side systems, microservices, REST/GraphQL APIs, databases, and platform infrastructure.",
        target_titles=[
            "Backend Developer",
            "Python Developer",
            "Software Engineer Backend",
            "FastAPI Developer",
            "API Developer",
            "Cloud Backend Engineer",
        ],
        relevance_keywords=[
            "Python",
            "FastAPI",
            "Flask",
            "Django",
            "REST",
            "GraphQL",
            "Microservices",
            "SQL",
            "Docker",
            "CI/CD",
            "Git",
            "Linux",
        ],
        domain_queries=[
            "Python Developer OR Backend Developer",
            "Software Engineer Backend OR API Engineer",
        ],
        forbidden_noise=[
            "wordpress",
            "joomla",
            "typo3 editor",
        ],
    ),
    "devsecops": DomainArchetype(
        slug="devsecops",
        name="DevSecOps & Cloud Security",
        description="Cloud infrastructure, container orchestration, CI/CD automation, security hardening, and observability.",
        target_titles=[
            "DevOps Engineer",
            "DevSecOps Engineer",
            "Cloud Security Engineer",
            "Platform Engineer",
            "Site Reliability Engineer",
            "Security Analyst",
        ],
        relevance_keywords=[
            "Kubernetes",
            "Docker",
            "Terraform",
            "CI/CD",
            "GitLab CI",
            "Jenkins",
            "AWS",
            "Linux",
            "OWASP",
            "Prometheus",
            "Grafana",
            "Splunk",
            "SIEM",
        ],
        domain_queries=[
            "DevSecOps Engineer OR Cloud Security",
            "DevOps Engineer OR Platform Engineer",
            "Site Reliability Engineer OR SRE",
        ],
        forbidden_noise=[
            "it support 1st level",
            "helpdesk agent",
        ],
    ),
    "general_engineering": DomainArchetype(
        slug="general_engineering",
        name="General Engineering & Applied Technology",
        description="Cross-disciplinary engineering, technical project management, and applied technology.",
        target_titles=[
            "Projektingenieur",
            "Ingenieur",
            "Project Engineer",
            "Junior Engineer",
            "Entwicklungsingenieur",
            "Technical Specialist",
        ],
        relevance_keywords=[
            "Projektmanagement",
            "Dokumentation",
            "Qualitätsmanagement",
            "Testing",
            "Inbetriebnahme",
            "Engineering",
        ],
        domain_queries=[
            "Projektingenieur OR Project Engineer",
            "Entwicklungsingenieur OR Junior Engineer",
        ],
        forbidden_noise=[
            "kaufmann",
            "sekretariat",
            "reinigungskraft",
        ],
    ),
}


def get_archetype(slug: Optional[str]) -> DomainArchetype:
    """Retrieve archetype by slug or return general_engineering fallback."""
    if not slug:
        return ARCHETYPE_CATALOG["general_engineering"]
    normalized = slug.lower().strip().replace("-", "_").replace(" ", "_")
    return ARCHETYPE_CATALOG.get(normalized, ARCHETYPE_CATALOG["general_engineering"])


def list_archetypes() -> list[DomainArchetype]:
    """Return all available archetypes."""
    return list(ARCHETYPE_CATALOG.values())

DEFAULT_ROLE_FAMILIES = {
    "data_engineering": {
        "include_titles": ["data engineer", "analytics engineer", "data platform engineer"],
        "include_skills": ["python", "kafka", "flink", "etl", "elt", "data pipeline"],
    },
    "devsecops": {
        "include_titles": ["devops", "devsecops", "cloud engineer", "site reliability", "sre"],
        "include_skills": ["docker", "kubernetes", "terraform", "aws", "ci/cd", "linux"],
    },
    "cpp_integration": {
        "include_titles": ["c++", "embedded", "integration engineer"],
        "include_skills": ["c++", "cmake", "qt", "can bus", "embedded linux"],
    },
    "backend_platform": {
        "include_titles": ["backend", "python developer", "software engineer", "api developer"],
        "include_skills": ["fastapi", "flask", "rest api", "postgresql", "microservices"],
    },
}

DEFAULT_TARGET_PROFILES = {
    "data_engineering": {
        "headline": "Data Engineering",
        "target_titles": ["Data Engineer", "Analytics Engineer"],
        "priority_skills": ["Python", "ETL", "Kafka", "Flink"],
    },
    "devsecops": {
        "headline": "DevSecOps and Cloud Engineering",
        "target_titles": ["DevOps Engineer", "Cloud Engineer"],
        "priority_skills": ["Linux", "Docker", "CI/CD", "Cloud"],
    },
    "cpp_integration": {
        "headline": "C++ and Systems Integration",
        "target_titles": ["C++ Engineer", "Embedded Engineer"],
        "priority_skills": ["C++", "Linux", "CMake"],
    },
    "backend_platform": {
        "headline": "Backend and Platform Engineering",
        "target_titles": ["Backend Engineer", "Software Engineer"],
        "priority_skills": ["Python", "APIs", "SQL"],
    },
}

DEFAULT_TAXONOMY = {"role_families": DEFAULT_ROLE_FAMILIES}

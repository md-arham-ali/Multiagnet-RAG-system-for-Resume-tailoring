"""
Generate synthetic, randomized BULK TEST DATA for the knowledge base, following
the schemas in context/Schema.md. The content is plausible but entirely fictional
— its only purpose is to exercise the architecture (embedding, retrieval,
reranking, matching, verification) with realistic-shaped records.

Theme: a data-science / ML / blockchain-DeFi / quant persona, matching the
"Aave Analytics" example in the schema file.

Writes (N = 50 by default for every multi-example schema):
  knowledge_base/profile/projects.json
  knowledge_base/profile/work_experience.json
  knowledge_base/profile/education.json
  knowledge_base/profile/skills.json
  knowledge_base/profile/coursework.json
  knowledge_base/profile/achievements.json
  knowledge_base/profile/extracurriculars.json
  knowledge_base/documents/cv_examples.json
  knowledge_base/documents/cover_letter_examples.json
  knowledge_base/learning/correction_records.json
  knowledge_base/learning/agent_learnings.json
  knowledge_base/do_not_claim/do_not_claim.json   (curated, not random)

The CV-writing instruction set and agent prompt examples are saved verbatim by a
separate step (they are configs, not randomized data).

Library only, runs nothing on import. Entry point: generate().
Runner:  python scripts/generate_kb_data.py [--n 50] [--seed 42]
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "knowledge_base"

# --------------------------------------------------------------------------- #
# Value pools
# --------------------------------------------------------------------------- #
DOMAINS = ["DeFi", "Blockchain", "Data Analytics", "Machine Learning",
           "Deep Learning", "NLP", "Computer Vision", "Quantitative Finance",
           "Web3", "MLOps", "Data Engineering", "Fintech", "Risk Analytics",
           "Recommender Systems", "Time Series Forecasting", "Fraud Detection",
           "Credit Scoring", "Algorithmic Trading", "On-chain Analytics",
           "Smart Contracts"]

PROJECT_TYPES = ["Data Analytics", "Machine Learning", "Data Engineering",
                 "Research", "Web Application", "Automation", "Dashboard",
                 "ETL Pipeline", "Predictive Modeling", "NLP System"]

STATUSES = ["Completed", "In Progress", "Archived", "Maintained", "Prototype"]

DATA_SOURCES = ["Dune Analytics", "Aave V3", "Uniswap V3", "The Graph",
                "Etherscan", "CoinGecko API", "Binance API", "Kaggle",
                "Internal Postgres", "S3 Data Lake", "Snowflake", "BigQuery",
                "Kafka Stream", "REST API", "Web Scraping", "CSV Exports",
                "Compound Protocol", "Chainlink Oracles"]

STORAGE = ["CSV", "Parquet", "PostgreSQL", "MongoDB", "S3", "Snowflake",
           "BigQuery", "Redis", "SQLite", "Delta Lake"]

PROCESSING = ["Pandas", "NumPy", "PySpark", "Dask", "Polars", "SQL",
              "Airflow", "dbt", "Spark"]

LANGUAGES = ["Python", "SQL", "R", "Solidity", "JavaScript", "TypeScript",
             "Scala", "Java", "Go", "Bash"]

LIBRARIES = ["Pandas", "NumPy", "Scikit-Learn", "PyTorch", "TensorFlow",
             "XGBoost", "LightGBM", "Matplotlib", "Seaborn", "Plotly",
             "Statsmodels", "SciPy", "NLTK", "spaCy", "Transformers",
             "LangChain", "web3.py", "Streamlit", "FastAPI"]

FRAMEWORKS = ["FastAPI", "Flask", "Django", "Streamlit", "React", "Next.js",
              "Hardhat", "Foundry", "PyTorch Lightning", "Hugging Face"]

TOOLS = ["Dune Analytics", "Tableau", "Power BI", "Docker", "Kubernetes",
         "Airflow", "MLflow", "Weights & Biases", "Git", "Jupyter", "DBeaver",
         "Grafana", "dbt", "Terraform"]

ALGORITHMS = ["Linear Regression", "Logistic Regression", "Random Forest",
              "XGBoost", "LightGBM", "K-Means", "DBSCAN", "ARIMA", "LSTM",
              "Transformer", "Gradient Boosting", "SVM", "Naive Bayes", "PCA",
              "Isolation Forest", "Prophet"]

EVAL_METRICS = ["RMSE", "MAE", "R2", "Accuracy", "Precision", "Recall", "F1",
                "AUC-ROC", "Log Loss", "Silhouette Score", "MAPE", "Sharpe Ratio"]

SKILLS = ["SQL", "Python", "Feature Engineering", "Data Visualization",
          "Statistical Modeling", "Machine Learning", "Deep Learning",
          "Time Series Analysis", "Data Wrangling", "ETL", "Cloud Computing",
          "Smart Contract Analysis", "On-chain Data", "Risk Modeling",
          "A/B Testing", "NLP", "MLOps", "Data Pipeline Design", "Dashboarding",
          "Model Deployment", "Anomaly Detection", "Prompt Engineering"]

SKILL_CATEGORIES = ["Programming Language", "ML Framework", "Data Tool",
                    "Cloud Platform", "Database", "Domain Knowledge",
                    "Soft Skill", "DevOps", "Visualization", "Blockchain"]

PROFICIENCY = ["Beginner", "Intermediate", "Advanced", "Expert"]

COMPANIES = ["BlockMetrics Labs", "DeFiPulse Analytics", "QuantEdge Capital",
             "DataForge Inc", "ChainSight", "Ledger Insights", "Nexus Data",
             "Helios Trading", "Orbit Analytics", "Tessellate AI",
             "Vertex Quant", "Meridian Data Labs", "OnChain Research",
             "Polaris Fintech", "Cobalt Analytics", "Aurora Web3",
             "Strata Intelligence", "Quanta Systems", "Pinnacle Data Co",
             "Northwind Analytics", "Catalyst Labs", "Beacon Quant",
             "Summit ML", "Ridgeline Data", "Horizon DeFi"]

ROLES = ["Data Scientist", "Machine Learning Engineer", "Data Analyst",
         "Quantitative Analyst", "Blockchain Data Engineer", "Research Engineer",
         "Data Engineer", "Analytics Engineer", "ML Researcher",
         "Business Intelligence Analyst", "Quant Developer"]

EMPLOYMENT_TYPES = ["Full-time", "Part-time", "Internship", "Contract", "Freelance"]

LOCATIONS = ["Remote", "New York, NY", "San Francisco, CA", "London, UK",
             "Berlin, DE", "Singapore", "Toronto, CA", "Dubai, UAE",
             "Bangalore, IN", "Austin, TX", "Lahore, PK", "Amsterdam, NL"]

UNIVERSITIES = ["State University of Technology", "Riverside Institute of Technology",
                "National University of Computer Science", "Metropolitan University",
                "Cascade Institute of Science", "Lakeside Technical University",
                "Granite State University", "Eastbrook University",
                "Summit College of Engineering", "Westfield University",
                "Highland Institute of Technology", "Crestwood University",
                "Fairmont University", "Pinegrove Institute of Science",
                "Brookfield University", "Ironwood Technical Institute"]

DEGREES = ["BSc", "BEng", "BS", "MSc", "MEng", "MS", "BBA"]

MAJORS = ["Computer Science", "Data Science", "Software Engineering",
          "Statistics", "Mathematics", "Financial Engineering",
          "Electrical Engineering", "Economics", "Information Systems",
          "Applied Mathematics", "Computational Finance"]

COURSES = ["Machine Learning", "Data Structures and Algorithms",
           "Database Systems", "Statistical Inference", "Deep Learning",
           "Blockchain and Cryptocurrencies", "Financial Mathematics",
           "Linear Algebra", "Probability Theory", "Distributed Systems",
           "Natural Language Processing", "Big Data Analytics",
           "Time Series Analysis", "Convex Optimization", "Computer Networks",
           "Operating Systems", "Reinforcement Learning", "Data Mining",
           "Cloud Computing", "Software Engineering"]

COURSE_TYPES = ["Core", "Elective", "Graduate", "Online (MOOC)", "Seminar"]
GRADES = ["A+", "A", "A-", "B+", "B"]
EDU_HONORS = ["Dean's List", "Top 5%", "Best Project Award", "Merit Scholarship",
              "Honor Roll", "Distinction"]

ACHIEVEMENT_CATEGORIES = ["Award", "Certification", "Competition", "Publication",
                          "Recognition", "Milestone", "Open Source", "Scholarship"]

ACTIVITY_NAMES = ["Data Science Club", "Blockchain Society", "Hackathon Team",
                  "ACM Student Chapter", "Quant Finance Group", "Open Source Circle",
                  "AI Reading Group", "Coding Bootcamp Mentor", "Math Olympiad Team",
                  "Tech Talks Organizer", "Volunteer Data Analyst", "Robotics Club"]

ORGS = ["University Student Union", "Local Tech Community", "Open Source Foundation",
        "Regional Hackathon", "Online Learning Cohort", "Nonprofit Data Collective"]

ACTION_WORDS = ["Engineered", "Developed", "Designed", "Implemented", "Optimized",
                "Automated", "Constructed", "Integrated", "Analyzed", "Created",
                "Built", "Enhanced", "Deployed", "Evaluated", "Streamlined",
                "Leveraged", "Generated", "Reduced", "Improved", "Accelerated"]

AGENTS = ["supervisor", "jd_analysis", "profile", "matching", "resume_writer",
          "cover_letter_writer", "critic", "verifier", "evaluation"]

INDUSTRIES = ["Fintech", "Crypto / Web3", "Banking", "Insurance", "E-commerce",
              "Healthcare Analytics", "AdTech", "Trading", "SaaS", "Consulting"]

COMPANY_TYPES = ["Early-stage Startup", "Scale-up", "Enterprise", "Hedge Fund",
                 "Big Tech", "Consultancy", "Research Lab"]

# Sentence fragments
PROBLEMS = ["fragmented data sources", "noisy on-chain data",
            "high false-positive rates", "slow batch pipelines",
            "manual reporting overhead", "sparse labeled data",
            "volatile market signals", "inconsistent schemas",
            "scaling bottlenecks", "delayed risk alerts"]
GOALS = ["surface at-risk loan positions", "forecast short-term volatility",
         "detect anomalous wallet behavior", "rank lending opportunities",
         "automate compliance reporting", "predict customer churn",
         "optimize gas usage", "classify token contracts",
         "map liquidity flows", "score credit risk"]
RESULT_NOUNS = ["accuracy", "latency", "coverage", "recall", "precision",
                "throughput", "turnaround time", "data freshness",
                "false-positive rate", "analyst hours"]
ORG_KINDS = ["a lending protocol", "a trading desk", "a fintech team",
             "an analytics group", "a risk function", "a research unit"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def pick(seq):
    return random.choice(seq)


def some(seq, lo, hi):
    k = random.randint(lo, min(hi, len(seq)))
    return random.sample(seq, k)


def pct():
    return random.randint(8, 92)


def big_num():
    return random.choice([f"{random.randint(1, 9)}.{random.randint(0, 9)}M",
                          f"{random.randint(10, 990)}K",
                          f"{random.randint(2, 50)}M",
                          f"{random.randint(100, 9000)}"])


def improve_pair():
    a = round(random.uniform(0.55, 0.78), 2)
    b = round(min(a + random.uniform(0.06, 0.2), 0.99), 2)
    return a, b


def ym(y0=2015, y1=2023):
    return f"{random.randint(y0, y1)}-{random.randint(1, 12):02d}"


def date_span(min_months=4, max_months=40, allow_present=True):
    sy = random.randint(2015, 2023)
    sm = random.randint(1, 12)
    start = f"{sy}-{sm:02d}"
    if allow_present and random.random() < 0.15:
        return start, "Present"
    months = random.randint(min_months, max_months)
    em = (sm - 1 + months) % 12 + 1
    ey = sy + (sm - 1 + months) // 12
    ey = min(ey, 2025)
    return start, f"{ey}-{em:02d}"


def iso_ts():
    base = datetime(2024, 1, 1) + timedelta(
        days=random.randint(0, 540), hours=random.randint(0, 23),
        minutes=random.randint(0, 59))
    return base.strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(text):
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")


def resume_bullets(domain, tools, skill):
    aw = random.sample(ACTION_WORDS, 5)
    t1, t2 = (tools + ["Python", "SQL"])[:2]
    a, b = improve_pair()
    return [
        f"{aw[0]} a {domain} solution to address {pick(PROBLEMS)}, targeting a "
        f"{pct()}% lift in {pick(RESULT_NOUNS)}.",
        f"{aw[1]} the workflow with {t1} and {t2}, achieving {pct()}% faster "
        f"{pick(RESULT_NOUNS)} on {big_num()} records.",
        f"{aw[2]} {skill} to refine the pipeline, improving {pick(EVAL_METRICS)} "
        f"from {a} to {b}.",
        f"{aw[3]} validation across {random.randint(3, 12)} datasets, cutting "
        f"{pick(RESULT_NOUNS)} by {pct()}%.",
        f"{aw[4]} the model into production, delivering a {pct()}% gain in "
        f"{pick(RESULT_NOUNS)} for {pick(ORG_KINDS)}.",
    ]


def qa(n, project=None):
    ctx = project or "the project"
    pool = [
        (f"Why did you choose {pick(LANGUAGES)} for {ctx}?",
         f"It fit the team's stack and offered strong {pick(LIBRARIES)} support, "
         f"which sped up {pick(GOALS)}."),
        (f"How did you handle {pick(PROBLEMS)}?",
         f"I {pick(ACTION_WORDS).lower()} a fix using {pick(TOOLS)}, which improved "
         f"{pick(RESULT_NOUNS)} by {pct()}%."),
        (f"What was the hardest part of {ctx}?",
         f"Dealing with {pick(PROBLEMS)}; I resolved it by {pick(ACTION_WORDS).lower()} "
         f"a {pick(ALGORITHMS)} baseline and iterating."),
        (f"How did you validate your results for {ctx}?",
         f"I tracked {pick(EVAL_METRICS)} and {pick(EVAL_METRICS)} with a held-out "
         f"split and monitored drift over {random.randint(3, 12)} months."),
        (f"What would you improve about {ctx}?",
         f"I'd add {pick(TOOLS)} for orchestration and test a {pick(ALGORITHMS)} model "
         f"to push {pick(RESULT_NOUNS)} further."),
    ]
    return [{"question": q, "answer": a} for q, a in random.sample(pool, min(n, len(pool)))]


# --------------------------------------------------------------------------- #
# Generators
# --------------------------------------------------------------------------- #
def gen_projects(n):
    subjects = ["Aave", "Uniswap", "Compound", "Ethereum", "DeFi Lending",
                "NFT Market", "Stablecoin", "Cross-chain", "Credit", "Customer",
                "Retail", "Crypto", "On-chain", "Lending Pool", "DEX", "Staking",
                "Derivatives", "Payments", "Loan", "Market", "Wallet", "Token"]
    nouns = ["Analytics Platform", "Risk Monitor", "Forecasting Engine",
             "Anomaly Detector", "Recommendation System", "Trading Bot",
             "Dashboard", "Data Pipeline", "Scoring Model", "Sentiment Tracker",
             "Liquidity Tracker", "Wallet Profiler", "Yield Optimizer",
             "Fraud Detector", "Churn Predictor", "Price Oracle",
             "Portfolio Analyzer", "Token Classifier", "Network Mapper"]
    used, out = set(), []
    for i in range(n):
        while True:
            title = f"{pick(subjects)} {pick(nouns)}"
            if title not in used:
                used.add(title)
                break
        domain = some(DOMAINS, 1, 3)
        libs = some(LIBRARIES, 2, 5)
        tools = some(TOOLS, 1, 3)
        skill = pick(SKILLS)
        a, b = improve_pair()
        goal = pick(GOALS)
        out.append({
            "project_id": f"{slug(title)}_{i:03d}",
            "basic_info": {
                "title": title,
                "type": pick(PROJECT_TYPES),
                "domain": domain,
                "status": pick(STATUSES),
            },
            "problem": {
                "business_problem": f"{pick(ORG_KINDS).capitalize()} needed to {goal} "
                                    f"despite {pick(PROBLEMS)}.",
                "technical_problem": f"{pick(PROBLEMS).capitalize()} across {big_num()} "
                                     f"records made {goal} unreliable.",
                "why_it_matters": f"Better {pick(RESULT_NOUNS)} directly reduces risk and "
                                  f"saves an estimated {pct()}% of {pick(RESULT_NOUNS)}.",
            },
            "architecture": {
                "data_sources": some(DATA_SOURCES, 1, 4),
                "storage": some(STORAGE, 1, 2),
                "processing": some(PROCESSING, 1, 3),
            },
            "technical_details": {
                "languages": some(LANGUAGES, 1, 3),
                "libraries": libs,
                "frameworks": some(FRAMEWORKS, 0, 2),
                "tools": tools,
            },
            "implementation": {
                "data_collection": {
                    "description": f"Collected and cleaned data from "
                                   f"{', '.join(some(DATA_SOURCES, 2, 3))}.",
                    "challenges": [f"Handling {pick(PROBLEMS)}",
                                   f"Reconciling {pick(PROBLEMS)}"],
                },
                "feature_engineering": {
                    "description": f"Engineered features to {goal}.",
                    "features_created": some(
                        ["rolling volatility", "utilization ratio", "wallet age",
                         "tx frequency", "liquidity depth", "z-score outliers",
                         "lag features", "moving averages", "health factor",
                         "gas percentile"], 3, 6),
                },
                "modeling": {
                    "algorithms": some(ALGORITHMS, 1, 3),
                    "evaluation": some(EVAL_METRICS, 2, 4),
                },
            },
            "metrics": {
                "features_created": random.randint(20, 120),
                "time_points": random.choice([180, 240, 360, 480, 720]),
            },
            "challenges": [
                {
                    "problem": f"{pick(PROBLEMS).capitalize()}.",
                    "solution": f"{pick(ACTION_WORDS)} a {pick(TOOLS)}-based fix.",
                    "learning": f"Learned to prioritize {pick(RESULT_NOUNS)} early.",
                }
                for _ in range(random.randint(1, 3))
            ],
            "interview_questions": qa(random.randint(2, 3), title),
            "resume_material": {
                "one_line": f"{pick(ACTION_WORDS)} a {pick(domain)} system to {goal}, "
                            f"improving {pick(EVAL_METRICS)} from {a} to {b}.",
                "two_line": f"Built an end-to-end {pick(domain)} pipeline using "
                            f"{', '.join(libs[:2])} to {goal}. Delivered a {pct()}% "
                            f"improvement in {pick(RESULT_NOUNS)}.",
                "full_bullet_points": resume_bullets(pick(domain), tools, skill),
            },
            "cover_letter_material": {
                "impact_story": f"I led work that helped {pick(ORG_KINDS)} {goal}, "
                                f"cutting {pick(RESULT_NOUNS)} by {pct()}%.",
                "technical_story": f"I {pick(ACTION_WORDS).lower()} a {pick(ALGORITHMS)} "
                                   f"model with {', '.join(libs[:2])} to solve "
                                   f"{pick(PROBLEMS)}.",
                "leadership_story": f"I coordinated {random.randint(2, 6)} contributors "
                                    f"and mentored juniors on {skill}.",
            },
            "skills_demonstrated": some(SKILLS, 3, 7),
        })
    return out


def gen_work(n, project_titles):
    out = []
    for i in range(n):
        role = pick(ROLES)
        company = pick(COMPANIES)
        start, end = date_span(6, 40)
        tech = some(LIBRARIES + TOOLS + LANGUAGES, 4, 8)
        out.append({
            "experience_id": f"exp_{i:03d}",
            "company": company,
            "role": role,
            "employment_type": pick(EMPLOYMENT_TYPES),
            "start_date": start,
            "end_date": end,
            "location": pick(LOCATIONS),
            "summary": f"Worked as a {role} at {company}, focused on "
                       f"{pick(GOALS)} for {pick(ORG_KINDS)}.",
            "responsibilities": [f"{pick(ACTION_WORDS)} pipelines to {pick(GOALS)}"
                                 for _ in range(random.randint(3, 5))],
            "technologies": tech,
            "achievements": [f"{pick(ACTION_WORDS)} a system that improved "
                             f"{pick(RESULT_NOUNS)} by {pct()}%"
                             for _ in range(random.randint(2, 4))],
            "metrics": [f"{pct()}% reduction in {pick(RESULT_NOUNS)}",
                        f"{big_num()} records processed daily"],
            "projects": random.sample(project_titles, random.randint(1, 3)),
            "skills_demonstrated": some(SKILLS, 4, 8),
            "resume_bullets": resume_bullets(pick(DOMAINS), some(TOOLS, 2, 3), pick(SKILLS)),
            "interview_questions": qa(random.randint(2, 3), f"your role at {company}"),
        })
    return out


def gen_education(n):
    out = []
    for i in range(n):
        inst = pick(UNIVERSITIES)
        start, end = date_span(36, 60, allow_present=False)
        out.append({
            "education_id": f"edu_{i:03d}",
            "institution": inst,
            "degree": pick(DEGREES),
            "major": pick(MAJORS),
            "start_date": start,
            "end_date": end,
            "cgpa": f"{round(random.uniform(3.0, 4.0), 2)}/4.0",
            "coursework": some(COURSES, 4, 8),
            "achievements": [f"{pick(EDU_HONORS)} in {random.randint(2016, 2024)}"
                             for _ in range(random.randint(1, 3))],
            "projects": [f"{pick(['Capstone', 'Thesis', 'Term'])} project on {pick(GOALS)}"
                         for _ in range(random.randint(1, 2))],
            "skills_gained": some(SKILLS, 4, 8),
        })
    return out


def gen_skills(n, project_ids, exp_ids):
    out = []
    names = list(dict.fromkeys(SKILLS + LIBRARIES + LANGUAGES))
    random.shuffle(names)
    for i in range(n):
        name = names[i % len(names)]
        out.append({
            "skill_id": f"skill_{i:03d}",
            "name": name,
            "category": pick(SKILL_CATEGORIES),
            "proficiency": pick(PROFICIENCY),
            "years_of_experience": random.randint(1, 8),
            "description": f"Applied {name} to {pick(GOALS)} across multiple projects.",
            "projects_used_in": random.sample(project_ids, random.randint(1, 4)),
            "work_experience_used_in": random.sample(exp_ids, random.randint(0, 3)),
            "coursework_related": some(COURSES, 1, 3),
            "evidence": [{"source": pick(["project", "work", "course", "competition"]),
                          "description": f"Used {name} to {pick(GOALS)}, improving "
                                         f"{pick(RESULT_NOUNS)} by {pct()}%."}
                         for _ in range(random.randint(1, 3))],
            "interview_topics": some([f"{name} internals", f"{name} trade-offs",
                                      f"scaling {name}", f"debugging {name}"], 1, 3),
            "subskills": some(SKILLS, 1, 4),
            "keywords": some([name] + SKILLS, 3, 6),
        })
    return out


def gen_coursework(n):
    out = []
    for i in range(n):
        cname = pick(COURSES)
        out.append({
            "course_id": f"course_{i:03d}",
            "course_name": cname,
            "institution": pick(UNIVERSITIES),
            "type": pick(COURSE_TYPES),
            "grade": pick(GRADES),
            "description": f"Covered {cname.lower()} with hands-on work on {pick(GOALS)}.",
            "topics": some(COURSES, 3, 6),
            "assignments": [f"Assignment on {pick(GOALS)}" for _ in range(random.randint(2, 4))],
            "projects": [f"Course project: {pick(GOALS)}" for _ in range(random.randint(1, 2))],
            "skills_gained": some(SKILLS, 2, 5),
            "relevance": {
                "ml": pick(["high", "medium", "low"]),
                "software": pick(["high", "medium", "low"]),
                "finance": pick(["high", "medium", "low"]),
                "blockchain": pick(["high", "medium", "low"]),
            },
            "keywords": some(SKILLS + [cname], 3, 6),
        })
    return out


def gen_achievements(n, project_ids):
    out = []
    for i in range(n):
        cat = pick(ACHIEVEMENT_CATEGORIES)
        title = {
            "Award": f"{pick(['Best', 'Outstanding', 'Top'])} {pick(['Project', 'Analyst', 'Hackathon'])} Award",
            "Certification": f"{pick(['Google', 'AWS', 'Coursera', 'DataCamp'])} {pick(['Data', 'ML', 'Analytics'])} Certificate",
            "Competition": f"{pick(['1st', '2nd', '3rd', 'Top 10'])} place — {pick(['Kaggle', 'DeFi', 'Quant'])} Challenge",
            "Publication": f"Blog/paper on {pick(GOALS)}",
            "Recognition": f"Recognized for {pick(GOALS)}",
            "Milestone": f"Shipped {pick(GOALS)} to production",
            "Open Source": f"Maintainer of a {pick(DOMAINS)} library",
            "Scholarship": f"{pick(['Merit', 'Need-based', 'Research'])} Scholarship",
        }[cat]
        out.append({
            "achievement_id": f"ach_{i:03d}",
            "title": title,
            "category": cat,
            "date": ym(2017, 2025),
            "description": f"{pick(ACTION_WORDS)} work that {pick(GOALS)}.",
            "impact": f"Improved {pick(RESULT_NOUNS)} by {pct()}% and saved {big_num()} in cost.",
            "metrics": [f"{pct()}% improvement in {pick(RESULT_NOUNS)}",
                        f"{big_num()} users/records impacted"],
            "skills_demonstrated": some(SKILLS, 2, 5),
            "related_projects": random.sample(project_ids, random.randint(0, 2)),
            "keywords": some(SKILLS + DOMAINS, 3, 6),
        })
    return out


def gen_extracurriculars(n):
    out = []
    for i in range(n):
        start, end = date_span(3, 30)
        out.append({
            "activity_id": f"act_{i:03d}",
            "activity_name": pick(ACTIVITY_NAMES),
            "role": pick(["Member", "Lead", "Organizer", "Mentor", "President", "Volunteer"]),
            "organization": pick(ORGS),
            "duration": f"{start} to {end}",
            "description": f"Contributed to {pick(GOALS)} and community learning.",
            "achievements": [f"{pick(ACTION_WORDS)} an initiative reaching {big_num()} people"
                             for _ in range(random.randint(1, 3))],
            "skills_demonstrated": some(SKILLS + ["Leadership", "Communication", "Teamwork"], 2, 5),
        })
    return out


def gen_cv_examples(n):
    # NOTE: context/Schema.md left "CV Example Schema" blank; this structure mirrors
    # the Cover Letter Example schema, with a generated multi-section CV body.
    out = []
    for i in range(n):
        role = pick(ROLES)
        ind = pick(INDUSTRIES)
        a, b = improve_pair()
        out.append({
            "example_id": f"cv_{i:03d}",
            "target_role": role,
            "industry": ind,
            "company_type": pick(COMPANY_TYPES),
            "seniority": pick(["Intern", "Junior", "Mid", "Senior", "Lead"]),
            "summary": f"{role} with strengths in {', '.join(some(SKILLS, 2, 3))} and a "
                       f"track record in {ind}.",
            "cv_text": (
                f"PROFESSIONAL SUMMARY\n{role} focused on {pick(GOALS)}.\n\n"
                f"EXPERIENCE\n- {pick(ACTION_WORDS)} a {pick(DOMAINS)} system, improving "
                f"{pick(EVAL_METRICS)} from {a} to {b}.\n- {pick(ACTION_WORDS)} pipelines "
                f"with {', '.join(some(TOOLS, 2, 3))}, cutting {pick(RESULT_NOUNS)} by {pct()}%.\n\n"
                f"SKILLS\n{', '.join(some(SKILLS, 5, 8))}"
            ),
            "strengths": some(["quantified impact", "clear structure", "ATS keywords",
                               "strong action verbs", "relevant domain focus",
                               "concise phrasing"], 2, 4),
            "score": round(random.uniform(6.5, 9.6), 1),
            "review_comments": some([
                "Strong use of metrics throughout.",
                "Could tighten the summary to two lines.",
                "Good keyword alignment with the target role.",
                "Add one more leadership example.",
                "Avoid repeating the same action verb.",
                "Quantify the last bullet.",
            ], 2, 4),
        })
    return out


def gen_cover_letters(n):
    out = []
    for i in range(n):
        role = pick(ROLES)
        ind = pick(INDUSTRIES)
        out.append({
            "example_id": f"cl_{i:03d}",
            "target_role": role,
            "industry": ind,
            "company_type": pick(COMPANY_TYPES),
            "cover_letter": (
                f"Dear Hiring Manager,\n\nI am excited to apply for the {role} role. "
                f"In my recent work I {pick(ACTION_WORDS).lower()} a {pick(DOMAINS)} "
                f"solution that {pick(GOALS)}, improving {pick(RESULT_NOUNS)} by {pct()}%. "
                f"I bring strong skills in {', '.join(some(SKILLS, 2, 3))} and a passion "
                f"for {ind}.\n\nI would welcome the chance to contribute to your team.\n\n"
                f"Sincerely,\nA. Candidate"
            ),
            "strengths": some(["personalized opening", "specific impact metric",
                               "clear motivation", "relevant skills", "concise",
                               "professional tone"], 2, 4),
            "score": round(random.uniform(6.0, 9.5), 1),
            "review_comments": some([
                "Good specific metric in paragraph one.",
                "Tie the closing back to the company mission.",
                "Slightly generic motivation — make it concrete.",
                "Strong, confident tone.",
                "Shorten the middle paragraph.",
            ], 2, 4),
        })
    return out


def gen_corrections(n):
    out = []
    for i in range(n):
        agent = pick(AGENTS)
        out.append({
            "correction_id": f"corr_{i:03d}",
            "agent_name": agent,
            "before": f"{pick(ACTION_WORDS)} a system that helped with {pick(GOALS)}.",
            "after": f"{pick(ACTION_WORDS)} a {pick(DOMAINS)} system that {pick(GOALS)}, "
                     f"improving {pick(RESULT_NOUNS)} by {pct()}%.",
            "feedback": pick([
                "Add a quantified result.",
                "Avoid repeating the action verb.",
                "Ground the claim in an actual project.",
                "Tighten to the word limit.",
                "Name the domain explicitly.",
                "Remove the unsupported metric.",
            ]),
            "reason": pick([
                "Missing numeric metric (validation rule).",
                "Action-word repetition across lines.",
                "Claim not supported by evidence.",
                "Exceeded the 18-word limit.",
                "Domain not stated.",
            ]),
            "timestamp": iso_ts(),
        })
    return out


def gen_learnings(n):
    cats = ["formatting", "factual-grounding", "quantification", "routing",
            "retrieval", "tone", "instruction-following"]
    mem_types = ["episodic", "semantic", "procedural"]
    out = []
    for i in range(n):
        agent = pick(AGENTS)
        role = pick(ROLES)
        ind = pick(INDUSTRIES)
        score = random.randint(3, 10)
        out.append({
            "learning_id": f"learn_{i:03d}",
            "agent_name": agent,
            "timestamp": iso_ts(),
            "task_type": pick(["resume_bullet", "cover_letter", "critique",
                               "verification", "routing", "jd_analysis"]),
            "project_context": f"{pick(DOMAINS)} — {pick(GOALS)}",
            "input_context": {
                "role": role,
                "industry": ind,
                "job_description_summary": f"Seeking a {role} with {', '.join(some(SKILLS, 2, 3))} "
                                          f"for {pick(GOALS)}.",
            },
            "task": f"Generate output for a {role} in {ind}.",
            "generated_output": f"{pick(ACTION_WORDS)} a {pick(DOMAINS)} system that "
                                f"{pick(GOALS)}, improving {pick(RESULT_NOUNS)} by {pct()}%.",
            "evaluation": {
                "score": score,
                "evaluation_source": pick(["human", "llm-judge", "automatic"]),
                "feedback": pick([
                    "Strong quantification.",
                    "Needs explicit domain mention.",
                    "Repeated action verbs.",
                    "Well grounded in evidence.",
                    "Too generic for the role.",
                ]),
                "strengths": some(["quantified", "concise", "grounded", "on-topic",
                                   "ATS-aligned"], 1, 3),
                "weaknesses": some(["verbose", "missing metric", "repetitive verbs",
                                    "weak domain focus", "unsupported claim"], 0, 3),
            },
            "reflection": {
                "root_cause": pick([
                    "Missing numeric anchor in the prompt.",
                    "Context window lacked the right exemplar.",
                    "Rubric weight on quantification too low.",
                    "Evidence not injected for the claim.",
                ]),
                "what_worked": some(["clear structure", "good exemplar", "tight prompt",
                                     "strong retrieval"], 1, 3),
                "what_failed": some(["over-generation", "no metric", "verb repetition",
                                     "hallucinated detail"], 0, 3),
                "what_should_change": some(["inject a metric requirement",
                                            "rerank exemplars by role",
                                            "enforce word limit",
                                            "add do-not-claim check"], 1, 3),
            },
            "lesson": {
                "summary": pick([
                    "Always anchor bullets with a numeric result.",
                    "Rerank exemplars by role type before injection.",
                    "Enforce unique action verbs per line.",
                    "Verify every metric against project evidence.",
                ]),
                "category": pick(cats),
                "confidence": round(random.uniform(0.4, 0.98), 2),
            },
            "reuse_conditions": {
                "roles": some(ROLES, 1, 3),
                "industries": some(INDUSTRIES, 1, 3),
                "project_types": some(PROJECT_TYPES, 1, 3),
                "minimum_similarity_score": round(random.uniform(0.6, 0.85), 2),
            },
            "memory_type": pick(mem_types),
            "should_reuse": score >= 6,
            "importance_score": random.randint(1, 10),
            "expiry_policy": {
                "review_after_days": random.choice([14, 30, 60, 90]),
                "auto_delete": random.random() < 0.2,
            },
            "embedding_text": f"{agent} learned to {pick(GOALS)} for a {role} in {ind} "
                              f"using {', '.join(some(SKILLS, 2, 3))}.",
            "metadata": {
                "version": "1.0",
                "tags": some(SKILLS + DOMAINS + cats, 2, 5),
            },
        })
    return out


def gen_do_not_claim():
    entries = [
        ("PhD in Computer Science", "Candidate holds an MSc, not a doctorate",
         ["phd", "ph.d", "doctorate", "doctoral"]),
        ("10+ years of industry experience", "Actual experience is under 6 years",
         ["10+ years", "ten years", "decade of experience"]),
        ("Worked at Google", "No employment at Google",
         ["google", "alphabet inc"]),
        ("Worked at Goldman Sachs", "No employment at Goldman Sachs",
         ["goldman sachs", "goldman"]),
        ("AWS Certified Solutions Architect", "Certification not obtained",
         ["aws certified", "solutions architect certification"]),
        ("Published at NeurIPS", "No NeurIPS publication",
         ["neurips", "nips proceedings"]),
        ("Led a team of 50 engineers", "Largest team led was 6",
         ["team of 50", "50 engineers", "50+ engineers"]),
        ("Fluent in Mandarin", "No Mandarin proficiency",
         ["fluent in mandarin", "native mandarin"]),
        ("CFA charterholder", "Not a CFA charterholder",
         ["cfa charterholder", "chartered financial analyst"]),
        ("Built a system serving 1B requests/day", "Real scale was ~5M/day",
         ["1b requests", "billion requests"]),
        ("Holds an active security clearance", "No security clearance held",
         ["security clearance", "top secret clearance"]),
        ("Founded a venture-backed startup", "Never founded a company",
         ["founded a startup", "co-founder of", "venture-backed"]),
        ("Expert-level Rust developer", "Beginner-level Rust only",
         ["expert in rust", "rust expert"]),
        ("Holds a granted US patent", "No patents filed or granted",
         ["patent holder", "granted patent", "us patent"]),
        ("Managed a $100M portfolio", "Never managed a portfolio of that size",
         ["$100m", "100 million portfolio"]),
        ("Kaggle Grandmaster", "Highest tier reached is Expert",
         ["grandmaster", "kaggle grandmaster"]),
        ("PMP certified", "Not PMP certified",
         ["pmp", "project management professional"]),
        ("MBA from an Ivy League school", "No MBA held",
         ["mba", "ivy league mba"]),
        ("Contributed to the Linux kernel", "No Linux kernel contributions",
         ["linux kernel", "kernel contributor"]),
        ("Native English speaker", "English is a second language",
         ["native english"]),
        ("Trained models on 1000 GPUs", "Largest run used 8 GPUs",
         ["1000 gpus", "thousand gpus"]),
        ("Holds a Series 7 license", "No Series 7 license",
         ["series 7"]),
    ]
    return {
        "_comment": "HARD-CONSTRAINT list. Injected WHOLE into the Document Agent and "
                    "the Verifier — never embedded, never retrieved top-k. Checked "
                    "exhaustively; a near-miss is a violation. (Synthetic test data.)",
        "version": 1,
        "forbidden_claims": [
            {"id": f"dnc_{i:03d}", "claim": c, "reason": r,
             "match": m, "match_mode": "fuzzy"}
            for i, (c, r, m) in enumerate(entries)
        ],
    }


# --------------------------------------------------------------------------- #
# Agent prompt examples  (Agents prompt examples Schema) — N per agent
# --------------------------------------------------------------------------- #
AGENT_ROSTER = ["supervisor", "jd_analysis", "profile", "matching",
                "resume_writer", "cover_letter_writer", "critic", "verifier",
                "evaluation"]

AGENT_ROLE = {
    "supervisor": "Workflow Coordinator",
    "jd_analysis": "Job Description Analyst",
    "profile": "Profile Retrieval & Gap-Interview Specialist",
    "matching": "Requirement-Evidence Matching Specialist",
    "resume_writer": "Resume Generation Specialist",
    "cover_letter_writer": "Cover Letter Specialist",
    "critic": "Output Reviewer",
    "verifier": "Fact Verification Agent",
    "evaluation": "Evaluation & Scoring Agent",
}

AGENT_OBJECTIVES = {
    "supervisor": ["Analyze user request", "Select appropriate agents",
                   "Retrieve required context", "Distribute context",
                   "Aggregate outputs", "Manage revision loops", "Enforce human gates"],
    "jd_analysis": ["Extract role and seniority", "Identify must-have requirements",
                    "Identify nice-to-have requirements", "Preserve exact ATS keywords",
                    "Output a validated requirements object", "Split compound bullets"],
    "profile": ["Retrieve relevant profile blocks", "Filter by skill or project category",
                "Identify evidence gaps", "Ask focused gap-interview questions",
                "Upsert new evidence", "Cite source ids"],
    "matching": ["Score evidence against requirements", "Assign support levels",
                 "Rank evidence for the writer", "List unmet must-haves",
                 "Produce a fit report", "Trace scores to source ids"],
    "resume_writer": ["Generate ATS-friendly resume content", "Match role requirements",
                      "Remain factually correct", "Quantify every bullet",
                      "Lead with strongest evidence"],
    "cover_letter_writer": ["Personalize the cover letter", "Demonstrate motivation",
                            "Highlight relevant experience", "Keep it concise",
                            "Tie experience to the role"],
    "critic": ["Review output against the rubric", "Score each dimension",
               "Surface concrete issues", "Recommend actionable fixes",
               "Return a pass or revise verdict"],
    "verifier": ["Prevent hallucinations", "Validate all claims",
                 "Enforce the do-not-claim list", "Report violations",
                 "Cite supporting evidence"],
    "evaluation": ["Score retrieval precision", "Compute ATS coverage",
                   "Assess generation quality", "Write to the Learning Store",
                   "Log prompt version and learning slice"],
}

AGENT_SYSTEM_BASE = {
    "supervisor": "You are the Supervisor of a multi-agent CV pipeline; you route work and never write the final output yourself.",
    "jd_analysis": "You are the JD Analysis Agent; you convert a raw job description into a typed, validated requirements object.",
    "profile": "You are the Profile Agent; you retrieve the candidate's strongest evidence and run a focused gap-interview.",
    "matching": "You are the Matching Agent; you score profile evidence against the requirements and produce a fit report.",
    "resume_writer": "You are the Resume Writer; you produce ATS-friendly, factually grounded resume bullets.",
    "cover_letter_writer": "You are the Cover Letter Writer; you craft a personalized, concise cover letter.",
    "critic": "You are the Critic; you review the writer's output against a rubric and return a typed verdict.",
    "verifier": "You are the Verifier; you check that every claim is grounded and violates no do-not-claim rule.",
    "evaluation": "You are the Evaluation Agent; you score the approved run and write exemplars to the Learning Store.",
}

AGENT_EMPHASIS = {
    "supervisor": ["Inject only the minimal context each agent needs.",
                   "Cap revision loops and escalate to a human gate when stuck.",
                   "Always inject the full do-not-claim list into the writer and verifier.",
                   "Prefer recent, high-scoring exemplars that match the role type.",
                   "Keep routing reasons short and auditable."],
    "jd_analysis": ["Never invent requirements not present in the text.",
                    "Preserve the JD's exact keyword phrasing for ATS.",
                    "Default ambiguous requirements to nice_to_have and flag them.",
                    "Return only the structured object, no prose."],
    "profile": ["Only use evidence that exists or that the candidate supplies.",
                "Distinguish strong, partial, and no evidence per requirement.",
                "Ask only about real gaps; never re-ask known facts.",
                "Attach a source id to every retrieved block."],
    "matching": ["Never upgrade a partial match to strong.",
                 "Do not introduce skills absent from the evidence.",
                 "Every score must be traceable to a source id.",
                 "Surface the honest unmet must-haves."],
    "resume_writer": ["Every claim must trace to a supplied profile block.",
                      "Mirror the JD's keywords only where truthful.",
                      "Use a unique action verb per line and quantify results.",
                      "Never state anything on the do-not-claim list."],
    "cover_letter_writer": ["Open with a specific, quantified impact.",
                            "Tie the closing to the company's mission.",
                            "Stay concise and professional.",
                            "Never invent motivation facts or experience."],
    "critic": ["Judge only against the rubric and supplied evidence.",
               "Give actionable instructions, not vague advice.",
               "Flag suspected ungrounded claims for the verifier.",
               "Do not rewrite the document yourself."],
    "verifier": ["Treat the do-not-claim list as exhaustive and absolute.",
                 "Label missing evidence as unsupported, not plausible.",
                 "Fail on any unsupported claim or do-not-claim hit.",
                 "Be precise about the offending location."],
    "evaluation": ["Be calibrated; the same output gets the same score.",
                   "Never reward output that skipped verification.",
                   "Consume the deterministic ATS score, don't re-estimate it.",
                   "Record prompt version and learning slice for attribution."],
}

AGENT_INSTRUCTIONS = {
    "supervisor": ["Classify the incoming task before routing.",
                   "Select the next agent based on the current stage.",
                   "Filter context by metadata, then rerank by similarity.",
                   "Truncate injected context to the token budget.",
                   "On critic 'revise', loop back to the writer (capped).",
                   "On verifier 'fail', loop back to the writer.",
                   "Run evaluation only after final approval."],
    "jd_analysis": ["List role_title and seniority first.",
                    "Separate must_have from nice_to_have.",
                    "Emit hard_skills and soft_skills as discrete items.",
                    "Copy ATS keywords verbatim, add a normalized form.",
                    "Capture explicit qualifications (degree, years).",
                    "Do not duplicate atomic requirements."],
    "profile": ["Retrieve the top evidence blocks per requirement.",
                "Filter retrieval by skill or project category.",
                "Mark each requirement strong / partial / none.",
                "Compose one focused question per real gap.",
                "Normalize gap answers into tagged profile blocks.",
                "Return evidence with source ids."],
    "matching": ["Rerank evidence before scoring.",
                 "Assign support = strong | partial | none.",
                 "Justify each score by citing the evidence block.",
                 "Compute overall fit and must_have coverage.",
                 "Rank evidence for the writer within a size budget.",
                 "List the unmet must-haves explicitly."],
    "resume_writer": ["Follow the cv_bullet_generation_v1 structure.",
                      "Start each line with a unique action verb.",
                      "Include at least three numeric mentions.",
                      "Stay within the 15-18 word limit per line.",
                      "Name the project domain explicitly.",
                      "Flag any requirement you cannot support."],
    "cover_letter_writer": ["Open with a hook tied to the role.",
                            "Cite one concrete, quantified achievement.",
                            "Connect skills to the job's needs.",
                            "Keep to three short paragraphs.",
                            "Close with a confident call to action."],
    "critic": ["Score relevance, evidence, template, ATS, readability.",
               "Assign a severity to each finding.",
               "Give a concrete location for each issue.",
               "Provide an actionable fix per 'revise' item.",
               "Return verdict = pass | revise."],
    "verifier": ["Extract every factual claim from the document.",
                 "Label each supported / unsupported / contradicted.",
                 "Cite the evidence id for supported claims.",
                 "Exact- and fuzzy-match the whole do-not-claim list.",
                 "Fail on any violation and report the location."],
    "evaluation": ["Compute retrieval precision over used evidence.",
                   "Consume the deterministic ATS coverage score.",
                   "Score fit against must-have coverage.",
                   "Judge generation quality with a short rationale.",
                   "Write the record with prompt versions and slice."],
}

AGENT_SUCCESS = {
    "supervisor": ["Routed to the correct agent on the first try.",
                   "Injected minimal, relevant context.",
                   "Caught a revision loop and escalated cleanly.",
                   "Selected a high-scoring role-matched exemplar."],
    "jd_analysis": ["Captured all must-haves without duplication.",
                    "Preserved exact ATS keyword phrasing.",
                    "Correctly split a compound requirement.",
                    "Flagged an ambiguous requirement."],
    "profile": ["Surfaced strong evidence for each requirement.",
                "Asked a single, answerable gap question.",
                "Filtered retrieval by the right category.",
                "Attached source ids to every block."],
    "matching": ["Scored honestly with no partial-to-strong inflation.",
                 "Traced every score to a source id.",
                 "Listed the real unmet must-haves.",
                 "Ranked the highest-signal evidence first."],
    "resume_writer": ["Every bullet quantified and grounded.",
                      "Unique action verbs across all lines.",
                      "Strong ATS keyword alignment.",
                      "Led with the most relevant evidence."],
    "cover_letter_writer": ["Opened with a specific metric.",
                            "Personalized to the company.",
                            "Concise and on-message.",
                            "Tied experience to the role."],
    "critic": ["Caught an ungrounded claim.",
               "Gave an actionable, specific fix.",
               "Scored consistently with the rubric.",
               "Returned a clear pass/revise verdict."],
    "verifier": ["Caught a hallucinated metric.",
                 "Blocked a do-not-claim violation.",
                 "Labeled missing evidence as unsupported.",
                 "Cited evidence for supported claims."],
    "evaluation": ["Scored calibrated and reproducibly.",
                   "Attributed a score change to the prompt version.",
                   "Flagged an exemplar-worthy run.",
                   "Logged the learning slice used."],
}

AGENT_FAILURE = {
    "supervisor": ["Leaked unnecessary context to an agent.",
                   "Missed a revision-loop cap and spun.",
                   "Routed to the wrong agent for the stage.",
                   "Injected a stale exemplar."],
    "jd_analysis": ["Invented a requirement not in the JD.",
                    "Normalized away an exact ATS keyword.",
                    "Merged two distinct requirements.",
                    "Returned prose instead of structured output."],
    "profile": ["Fabricated experience not in the store.",
                "Asked about a fact already known.",
                "Returned blocks without source ids.",
                "Over-retrieved irrelevant blocks."],
    "matching": ["Upgraded a partial match to strong.",
                 "Introduced a skill absent from evidence.",
                 "Gave an untraceable score.",
                 "Hid an unmet must-have."],
    "resume_writer": ["Wrote an unsupported claim.",
                      "Repeated an action verb across lines.",
                      "Exceeded the word limit.",
                      "Stated a do-not-claim item."],
    "cover_letter_writer": ["Used a generic, templated opening.",
                            "Invented a motivation fact.",
                            "Ran long and unfocused.",
                            "Overclaimed unrelated experience."],
    "critic": ["Invented a requirement not in the rubric.",
               "Gave vague advice like 'make it better'.",
               "Rewrote the document instead of reviewing.",
               "Missed an obvious formatting issue."],
    "verifier": ["Gave an unsupported claim the benefit of the doubt.",
                 "Missed a paraphrased do-not-claim violation.",
                 "Passed a document with a hallucinated metric.",
                 "Reported a vague, locationless violation."],
    "evaluation": ["Rewarded a run that skipped verification.",
                   "Re-estimated ATS instead of consuming it.",
                   "Scored the same output inconsistently.",
                   "Omitted the prompt version from the record."],
}

AGENT_LEARNING = {
    "supervisor": ["Tighten context budgets for the writer.",
                   "Rerank exemplars by role type before injection.",
                   "Lower the revision cap for simple roles."],
    "jd_analysis": ["Keep a stop-list of non-requirement phrases.",
                    "Always preserve multi-word keywords intact.",
                    "Prefer recall on must-haves."],
    "profile": ["Batch gap questions to reduce gate friction.",
                "Weight recent projects higher in retrieval.",
                "Tag upserted evidence with categories."],
    "matching": ["Penalize inflation in the scoring rubric.",
                 "Cap injected evidence by token budget.",
                 "Always expose unmet must-haves."],
    "resume_writer": ["Enforce a numeric-mention minimum.",
                      "Rotate action verbs from the approved list.",
                      "Inject the full do-not-claim list every pass."],
    "cover_letter_writer": ["Require one concrete metric per letter.",
                            "Keep a per-company personalization hook.",
                            "Trim to three paragraphs."],
    "critic": ["Weight quantification higher in the rubric.",
               "Require a location for every finding.",
               "Separate style flags from grounding flags."],
    "verifier": ["Default missing evidence to unsupported.",
                 "Fuzzy-match the whole do-not-claim list.",
                 "Demand precise offending locations."],
    "evaluation": ["Log prompt version with every score.",
                   "Reuse only high-scoring, verified exemplars.",
                   "Track Gemini call counts against the cap."],
}

# Verbatim seed templates from context/Schema.md (used as example #0 where present).
SEED_TEMPLATES = {
    "supervisor": {
        "agent_name": "supervisor", "version": "1.0", "role": "Workflow Coordinator",
        "objective": ["Analyze user request", "Select appropriate agents",
                      "Retrieve required context", "Distribute context", "Aggregate outputs"],
        "core_rules": ["Never generate final output", "Only coordinate agents",
                       "Minimize context leakage", "Provide only necessary information"],
        "retrieval_strategy": {"knowledge_sources": [], "max_chunks": 0, "reranking_enabled": True},
        "decision_framework": ["Classify task", "Select agent", "Select context", "Evaluate output"],
        "prompt_template": {"system": "", "instructions": [], "examples": []},
        "success_patterns": [], "failure_patterns": [], "learning_rules": [],
    },
    "resume_writer": {
        "agent_name": "resume_writer", "role": "Resume Generation Specialist",
        "objective": ["Generate ATS-friendly resume content", "Match role requirements",
                      "Remain factually correct"],
        "allowed_inputs": ["Projects", "Skills", "Achievements", "Examples"],
        "forbidden_actions": ["Invent achievements", "Invent experience", "Invent certifications"],
        "writing_rules": ["Use action verbs", "Quantify impact", "Maintain factual accuracy"],
        "prompt_template": {"system": "", "instructions": [], "few_shot_examples": []},
        "success_patterns": [], "failure_patterns": [], "learning_rules": [],
    },
    "cover_letter_writer": {
        "agent_name": "cover_letter_writer", "role": "Cover Letter Specialist",
        "objective": ["Personalize cover letter", "Demonstrate motivation",
                      "Highlight relevant experience"],
        "writing_style": {"professional": True, "personalized": True, "concise": True},
        "prompt_template": {},
        "success_patterns": [], "failure_patterns": [], "learning_rules": [],
    },
    "critic": {
        "agent_name": "critic", "role": "Output Reviewer",
        "objective": ["Review output against the rubric", "Score each dimension",
                      "Surface concrete issues", "Recommend actionable fixes",
                      "Return a pass or revise verdict"],
        "evaluation_dimensions": ["Accuracy", "Instruction Following", "Formatting",
                                  "Relevance", "Quantification"],
        "scoring_scale": {"min": 0, "max": 10},
        "required_outputs": ["Score", "Issues", "Recommendations"],
        "prompt_template": {},
        "success_patterns": [], "failure_patterns": [], "learning_rules": [],
    },
    "verifier": {
        "agent_name": "verifier", "role": "Fact Verification Agent",
        "objective": ["Prevent hallucinations", "Validate all claims"],
        "verification_sources": ["Projects", "Experience", "Education", "Skills"],
        "forbidden_claims_source": "constraints.json",
        "validation_checks": ["Project existence", "Metric existence", "Skill existence",
                              "Experience existence"],
        "required_output": {"approved": True, "violations": []},
        "prompt_template": {},
        "success_patterns": [], "failure_patterns": [], "learning_rules": [],
    },
}


def agent_specific(agent):
    if agent == "supervisor":
        return {
            "core_rules": ["Never generate final output", "Only coordinate agents",
                           "Minimize context leakage", "Provide only necessary information"],
            "retrieval_strategy": {
                "knowledge_sources": some(["profile", "documents", "learning", "do_not_claim"], 1, 4),
                "max_chunks": random.choice([3, 5, 8, 10]),
                "reranking_enabled": True,
            },
            "decision_framework": ["Classify task", "Select agent", "Select context", "Evaluate output"],
        }
    if agent == "jd_analysis":
        return {
            "extraction_targets": ["role_title", "seniority", "must_have", "nice_to_have", "keywords"],
            "output_format": "structured_requirements",
            "core_rules": ["Extract only what is present", "Preserve exact keyword phrasing",
                           "Split compound bullets"],
        }
    if agent == "profile":
        return {
            "retrieval_sources": some(["projects", "work_experience", "skills", "achievements", "education"], 2, 5),
            "gap_interview_rules": ["Ask only about real gaps", "One focused question per gap",
                                    "Batch related questions"],
            "core_rules": ["Never fabricate evidence", "Cite source ids"],
        }
    if agent == "matching":
        return {
            "scoring_dimensions": ["must_have_coverage", "overall_fit"],
            "support_levels": ["strong", "partial", "none"],
            "core_rules": ["Never upgrade partial to strong", "Trace every score to a source id"],
        }
    if agent == "resume_writer":
        return {
            "allowed_inputs": ["Projects", "Skills", "Achievements", "Examples"],
            "forbidden_actions": ["Invent achievements", "Invent experience", "Invent certifications"],
            "writing_rules": ["Use action verbs", "Quantify impact", "Maintain factual accuracy",
                              "Unique action verb per line"],
            "instruction_set": "cv_bullet_generation_v1",
        }
    if agent == "cover_letter_writer":
        return {
            "writing_style": {"professional": True, "personalized": True, "concise": True},
            "allowed_inputs": ["Projects", "Achievements", "Job Description"],
            "forbidden_actions": ["Invent motivation facts", "Overclaim experience"],
        }
    if agent == "critic":
        return {
            "evaluation_dimensions": ["Accuracy", "Instruction Following", "Formatting",
                                      "Relevance", "Quantification"],
            "scoring_scale": {"min": 0, "max": 10},
            "required_outputs": ["Score", "Issues", "Recommendations"],
        }
    if agent == "verifier":
        return {
            "verification_sources": ["Projects", "Experience", "Education", "Skills"],
            "forbidden_claims_source": "do_not_claim.json",
            "validation_checks": ["Project existence", "Metric existence", "Skill existence",
                                  "Experience existence"],
            "required_output": {"approved": True, "violations": []},
        }
    if agent == "evaluation":
        return {
            "metrics": ["retrieval_precision", "ats_coverage", "fit_score", "generation_quality"],
            "scoring_scale": {"min": 0, "max": 10},
            "writes_to": "learning_store",
        }
    return {}


def few_shot(agent, k=None):
    k = k or random.randint(1, 3)
    out = []
    for _ in range(k):
        role = pick(ROLES)
        dom = pick(DOMAINS)
        goal = pick(GOALS)
        skill = pick(SKILLS)
        ind = pick(INDUSTRIES)
        if agent == "supervisor":
            inp = f"User wants a CV for a {role} role in {ind}."
            outp = ("Route -> jd_analysis (inject job_description); then profile, "
                    "matching, resume_writer, critic, verifier.")
        elif agent == "jd_analysis":
            inp = f"JD excerpt: 'Seeking a {role} skilled in {skill} and {pick(SKILLS)} to {goal}.'"
            outp = f"role_title={role}; must_have=[{skill}]; keywords=[{skill}, {pick(SKILLS)}]"
        elif agent == "profile":
            inp = f"Requirement: {skill} for {goal}."
            outp = f"retrieved=[proj_x, exp_y]; support=partial; gap_question='How deep is your {skill} work?'"
        elif agent == "matching":
            inp = f"Requirement: {skill}. Evidence: a {dom} project applying {skill}."
            outp = f"support=strong; evidence_ids=[proj_x]; justification='proj_x applied {skill} to {goal}'."
        elif agent == "resume_writer":
            inp = f"Project: a {dom} system to {goal}; target role: {role}."
            outp = resume_bullets(dom, some(TOOLS, 2, 3), skill)[0]
        elif agent == "cover_letter_writer":
            inp = f"Role: {role} at a {pick(COMPANY_TYPES)} in {ind}."
            outp = (f"'I am excited to apply for the {role} role; I recently "
                    f"{pick(ACTION_WORDS).lower()} a {dom} system that {goal}.'")
        elif agent == "critic":
            inp = f"Draft bullet: 'Built a {dom} system for {goal}.'"
            outp = ("verdict=revise; issues=['no metric','generic verb']; "
                    "recommendations=['add a quantified result','use a stronger action verb'].")
        elif agent == "verifier":
            inp = f"Claim: 'Improved {pick(RESULT_NOUNS)} by {pct()}%.' Evidence: project metrics."
            outp = "label=supported; evidence_id=proj_x; do_not_claim_hits=[]."
        else:  # evaluation
            inp = f"Approved run: {role} CV in {ind}; ATS coverage precomputed."
            outp = (f"scores={{ats:{round(random.uniform(0.5, 0.95), 2)}, "
                    f"fit:{round(random.uniform(0.5, 0.95), 2)}, "
                    f"faithfulness:{round(random.uniform(0.6, 0.99), 2)}}}; "
                    f"exemplar_worthy={random.random() > 0.5}")
        out.append({"input": inp, "output": outp})
    return out


def make_agent_example(agent, i):
    objs = AGENT_OBJECTIVES[agent]
    instrs = AGENT_INSTRUCTIONS[agent]
    rec = {
        "example_id": f"{agent}_prompt_{i:03d}",
        "agent_name": agent,
        "version": pick(["1.0", "1.0", "1.0", "1.1", "1.2", "2.0"]),
        "role": AGENT_ROLE[agent],
        "objective": some(objs, 3, 5),
    }
    rec.update(agent_specific(agent))
    rec["prompt_template"] = {
        "system": f"{AGENT_SYSTEM_BASE[agent]} {pick(AGENT_EMPHASIS[agent])}",
        "instructions": some(instrs, 3, 6),
        "few_shot_examples": few_shot(agent),
    }
    rec["success_patterns"] = some(AGENT_SUCCESS[agent], 2, 4)
    rec["failure_patterns"] = some(AGENT_FAILURE[agent], 2, 4)
    rec["learning_rules"] = some(AGENT_LEARNING[agent], 1, 3)
    return rec


def gen_agent_examples(agent, n):
    out = []
    seed = SEED_TEMPLATES.get(agent)
    if seed:
        out.append({"example_id": f"{agent}_prompt_000", **seed})
    for i in range(len(out), n):
        out.append(make_agent_example(agent, i))
    return out


# --------------------------------------------------------------------------- #
# Write
# --------------------------------------------------------------------------- #
def write_json(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(obj) if isinstance(obj, list) else 1


def generate(n: int = 50, small: int = 10, agent_n: int = 50, seed: int = 42,
             kb_dir: Path = KB) -> dict[Path, int]:
    """Write every fixture file under kb_dir. Returns {path: count}, count = 1 for curated files.
    small = education / coursework / extracurriculars, agent_n = prompt examples per agent."""
    random.seed(seed)  # every gen_* draws from the module-level RNG
    n, small, agent_n = max(n, 1), max(small, 1), max(agent_n, 1)

    projects = gen_projects(n)
    pids = [p["project_id"] for p in projects]
    ptitles = [p["basic_info"]["title"] for p in projects]
    work = gen_work(n, ptitles)
    eids = [w["experience_id"] for w in work]

    files = {
        kb_dir / "profile" / "projects.json": projects,
        kb_dir / "profile" / "work_experience.json": work,
        kb_dir / "profile" / "education.json": gen_education(small),
        kb_dir / "profile" / "skills.json": gen_skills(n, pids, eids),
        kb_dir / "profile" / "coursework.json": gen_coursework(small),
        kb_dir / "profile" / "achievements.json": gen_achievements(n, pids),
        kb_dir / "profile" / "extracurriculars.json": gen_extracurriculars(small),
        kb_dir / "documents" / "cv_examples.json": gen_cv_examples(n),
        kb_dir / "documents" / "cover_letter_examples.json": gen_cover_letters(n),
        kb_dir / "learning" / "correction_records.json": gen_corrections(n),
        kb_dir / "learning" / "agent_learnings.json": gen_learnings(n),
        kb_dir / "do_not_claim" / "do_not_claim.json": gen_do_not_claim(),
    }
    # agent prompt examples, one file per agent
    ap_dir = kb_dir / "agent_prompts"
    for agent in AGENT_ROSTER:
        files[ap_dir / f"{agent}.json"] = gen_agent_examples(agent, agent_n)

    # old combined file, superseded by the per-agent files
    (ap_dir / "agent_prompt_examples.json").unlink(missing_ok=True)
    return {path: write_json(path, obj) for path, obj in files.items()}

def get_projects():
    # Each tuple: (section, category, subsection, title, byline, tag,
    #   summary, description, date_label, date_value, deliverables,
    #   challenges, future_improvements, extra_notes, image_path,
    #   external_link)
    return [
        (
            "project", "Web Development", None,
            "21 Threads - eCommerce Digital Transformation",
            "Rone Peh", "Web Development - Flask",
            "Collaborative digital transformation project following Design Thinking principles.",
            "Built account management, Matplotlib data analysis, OpenAI chatbot, cloud hosting, "
            "and SMTP order notifications using Python Flask, Bootstrap, JavaScript, and APIs.",
            "Period", "Oct 2023 - Feb 2024",
            "Account system, data viz, AI chatbot, cloud deployment, email notifications",
            "Integrating multiple APIs and ensuring security across modules",
            "Add recommendation engine", "",
            "../static/images/Projects/AppDev_AdaptEd.png", "",
        ),
        (
            "project", "Innovation", None,
            "Eluminate - Regenerative Business Model",
            "International Bootcamp 2024", "Innovation - Sustainability",
            "Waste-powered street lighting system developed during International Bootcamp 2024 in Bangkok.",
            "Designed Eluminate integrating Design Thinking. Won Most Innovative Solution award. "
            "Presented to industry practitioners from New Energy Nexus, True Incube, and Cube Asia.",
            "Period", "Mar 2024",
            "Prototype, go-to-market strategy, pitch presentation",
            "Cross-cultural collaboration and rapid prototyping",
            "Scale pilot deployment", "Most Innovative Solution award",
            "", "",
        ),
        (
            "project", "Web Development", None,
            "Sustainify - Eco-Conscious Gamification Platform",
            "Rone Peh", "Web Development - Full Stack",
            "Web platform gamifying sustainability through daily challenges and community engagement.",
            "Led Account Management module development. Implemented challenge tracking, friend "
            "interaction, point-based rewards. Built admin dashboard and analytics tools.",
            "Period", "Apr 2024 - Jul 2024",
            "Account management, gamification features, admin dashboard",
            "Holistic integration across 5 team modules",
            "Mobile app version", "",
            "", "https://www.figma.com/design/ADjQrHYusSixXMvlwPJOcE",
        ),
        (
            "project", "AI / ML", None,
            "SDG Open Hack 2025 - Synergise",
            "Team OTY", "AI / ML - Sustainability",
            "AI-driven matchmaking platform for industrial waste exchange targeting Net-Zero.",
            "Architected platform with AI-driven matchmaking and IoT monitoring to help "
            "industrial yards find profitable outlets for waste. Model showed 10-15% CO2 reduction.",
            "Period", "Oct 2025",
            "AI matchmaking, IoT monitoring, marketplace platform",
            "Tracking difficult Scope 3 emissions",
            "Expand to more industrial zones", "",
            "", "",
        ),
        (
            "project", "AI / ML", None,
            "Jira Recall - AI-Powered Ticket Search Engine",
            "Rone Peh", "AI / ML - Full Stack",
            "Intelligent search app combining TF-IDF and LLM for Jira ticket retrieval.",
            "Hybrid search with TF-IDF + LLM semantic understanding. Achieved 20x latency "
            "improvement. React/TypeScript frontend with search history and CSV export. "
            "Automated Jira REST API scraping pipeline.",
            "Period", "Jan 2026 - Mar 2026",
            "Hybrid search, NLP queries, React frontend, data pipeline",
            "Balancing search relevance with latency",
            "Add team-level analytics", "",
            "", "",
        ),
    ]

"""
Mock Data Generator - Industry-specific fake data templates
Generates realistic test data for developers who don't have data
"""
from faker import Faker
import random
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any

fake = Faker()


class DataTemplate:
    """Base class for data templates"""

    def generate(self, count: int = 100) -> List[Dict[str, Any]]:
        """Generate N records of fake data"""
        raise NotImplementedError


# ============================================================================
# MEDICAL DATA TEMPLATES
# ============================================================================

class FakeMedicalData(DataTemplate):
    """Generate fake medical/healthcare data"""

    DIAGNOSES = [
        "Hypertension", "Type 2 Diabetes", "Asthma", "COPD",
        "Depression", "Anxiety", "Migraine", "Arthritis",
        "Coronary Artery Disease", "Pneumonia"
    ]

    MEDICATIONS = [
        "Lisinopril", "Metformin", "Atorvastatin", "Levothyroxine",
        "Amlodipine", "Omeprazole", "Albuterol", "Gabapentin"
    ]

    def generate_patients(self, count: int = 100) -> List[Dict]:
        """Generate fake patient records"""
        patients = []
        for i in range(count):
            dob = fake.date_of_birth(minimum_age=18, maximum_age=90)
            patients.append({
                "patient_id": f"PT-{i+1:06d}",
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "date_of_birth": dob.isoformat(),
                "age": (datetime.now().date() - dob).days // 365,
                "gender": random.choice(["M", "F", "Other"]),
                "blood_type": random.choice(["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]),
                "email": fake.email(),
                "phone": fake.phone_number(),
                "address": fake.address().replace("\n", ", "),
                "insurance": f"INS-{fake.bothify('??-########')}",
                "primary_physician": fake.name(),
                "allergies": random.sample(["Penicillin", "Latex", "Peanuts", "Shellfish", "None"], k=random.randint(0, 2)),
                "chronic_conditions": random.sample(self.DIAGNOSES, k=random.randint(0, 3))
            })
        return patients

    def generate_appointments(self, patient_ids: List[str], count: int = 200) -> List[Dict]:
        """Generate fake appointment records"""
        appointments = []
        for i in range(count):
            apt_date = fake.date_time_between(start_date="-30d", end_date="+30d")
            appointments.append({
                "appointment_id": f"APT-{i+1:06d}",
                "patient_id": random.choice(patient_ids),
                "provider": fake.name(),
                "specialty": random.choice(["Cardiology", "Dermatology", "Internal Medicine", "Orthopedics", "Pediatrics"]),
                "appointment_date": apt_date.isoformat(),
                "status": random.choice(["Scheduled", "Completed", "Cancelled", "No-Show"]),
                "reason": random.choice(["Annual Checkup", "Follow-up", "Urgent Care", "Consultation"]),
                "duration_minutes": random.choice([15, 30, 45, 60]),
                "notes": fake.text(max_nb_chars=200)
            })
        return appointments

    def generate_prescriptions(self, patient_ids: List[str], count: int = 150) -> List[Dict]:
        """Generate fake prescription records"""
        prescriptions = []
        for i in range(count):
            prescriptions.append({
                "prescription_id": f"RX-{i+1:06d}",
                "patient_id": random.choice(patient_ids),
                "medication": random.choice(self.MEDICATIONS),
                "dosage": f"{random.choice([5, 10, 20, 40, 50])}mg",
                "frequency": random.choice(["Once daily", "Twice daily", "Three times daily", "As needed"]),
                "quantity": random.randint(30, 90),
                "refills": random.randint(0, 6),
                "prescribed_by": fake.name(),
                "prescribed_date": fake.date_between(start_date="-60d", end_date="today").isoformat(),
                "pharmacy": fake.company() + " Pharmacy",
                "instructions": fake.text(max_nb_chars=100)
            })
        return prescriptions


# ============================================================================
# CRIME DATA TEMPLATES
# ============================================================================

class FakeCrimeData(DataTemplate):
    """Generate fake crime/law enforcement data"""

    CRIME_TYPES = [
        "Burglary", "Theft", "Assault", "Vandalism", "Drug Possession",
        "Fraud", "Robbery", "Domestic Violence", "DUI", "Trespassing"
    ]

    def generate_incidents(self, count: int = 100) -> List[Dict]:
        """Generate fake crime incident reports"""
        incidents = []
        for i in range(count):
            incident_date = fake.date_time_between(start_date="-90d", end_date="now")
            incidents.append({
                "incident_id": f"INC-{fake.bothify('####-??????')}",
                "case_number": f"CASE-{i+1:06d}",
                "crime_type": random.choice(self.CRIME_TYPES),
                "severity": random.choice(["Misdemeanor", "Felony", "Infraction"]),
                "incident_date": incident_date.isoformat(),
                "reported_date": (incident_date + timedelta(hours=random.randint(1, 48))).isoformat(),
                "location": {
                    "address": fake.street_address(),
                    "city": fake.city(),
                    "state": fake.state_abbr(),
                    "zip": fake.zipcode(),
                    "latitude": float(fake.latitude()),
                    "longitude": float(fake.longitude())
                },
                "reporting_officer": {
                    "badge": f"BADGE-{random.randint(1000, 9999)}",
                    "name": fake.name(),
                    "rank": random.choice(["Officer", "Detective", "Sergeant", "Lieutenant"])
                },
                "status": random.choice(["Open", "Under Investigation", "Closed", "Cold Case"]),
                "description": fake.text(max_nb_chars=300),
                "evidence_collected": random.choice([True, False]),
                "witnesses": random.randint(0, 5)
            })
        return incidents

    def generate_suspects(self, incident_ids: List[str], count: int = 75) -> List[Dict]:
        """Generate fake suspect records"""
        suspects = []
        for i in range(count):
            suspects.append({
                "suspect_id": f"SUSP-{i+1:06d}",
                "incident_id": random.choice(incident_ids),
                "name": fake.name(),
                "alias": fake.user_name() if random.random() > 0.7 else None,
                "age": random.randint(18, 65),
                "gender": random.choice(["M", "F"]),
                "race": random.choice(["White", "Black", "Hispanic", "Asian", "Other"]),
                "height": f"{random.randint(60, 76)}\"",
                "weight": f"{random.randint(120, 250)} lbs",
                "hair_color": random.choice(["Black", "Brown", "Blonde", "Red", "Gray"]),
                "eye_color": random.choice(["Brown", "Blue", "Green", "Hazel"]),
                "address": fake.address().replace("\n", ", ") if random.random() > 0.3 else "Unknown",
                "prior_arrests": random.randint(0, 10),
                "status": random.choice(["Person of Interest", "Arrested", "Wanted", "Cleared"]),
                "notes": fake.text(max_nb_chars=200)
            })
        return suspects


# ============================================================================
# IT DATA TEMPLATES
# ============================================================================

class FakeITData(DataTemplate):
    """Generate fake IT infrastructure data"""

    def generate_servers(self, count: int = 50) -> List[Dict]:
        """Generate fake server inventory"""
        servers = []
        for i in range(count):
            servers.append({
                "server_id": f"SRV-{i+1:04d}",
                "hostname": f"{random.choice(['web', 'app', 'db', 'cache', 'api'])}-{fake.word()}-{random.randint(1,99)}",
                "ip_address": fake.ipv4_private(),
                "public_ip": fake.ipv4_public() if random.random() > 0.5 else None,
                "os": random.choice([
                    "Ubuntu 22.04 LTS",
                    "CentOS 8",
                    "Red Hat Enterprise Linux 8",
                    "Windows Server 2019",
                    "Debian 11"
                ]),
                "cpu_cores": random.choice([2, 4, 8, 16, 32]),
                "ram_gb": random.choice([8, 16, 32, 64, 128]),
                "disk_gb": random.choice([100, 250, 500, 1000, 2000]),
                "location": random.choice(["us-east-1", "us-west-2", "eu-central-1", "ap-southeast-1"]),
                "environment": random.choice(["Production", "Staging", "Development", "QA"]),
                "status": random.choice(["Running", "Stopped", "Maintenance"]),
                "uptime_hours": random.randint(1, 8760),
                "last_patched": fake.date_between(start_date="-60d").isoformat(),
                "tags": random.sample(["web", "database", "cache", "api", "critical", "deprecated"], k=random.randint(1, 3))
            })
        return servers

    def generate_applications(self, count: int = 30) -> List[Dict]:
        """Generate fake application inventory"""
        apps = []
        for i in range(count):
            apps.append({
                "app_id": f"APP-{i+1:04d}",
                "name": fake.catch_phrase().replace(" ", "-").lower(),
                "version": f"{random.randint(1,5)}.{random.randint(0,20)}.{random.randint(0,50)}",
                "language": random.choice(["Python", "Java", "Node.js", "Go", "Ruby", "PHP", ".NET"]),
                "framework": random.choice(["Django", "Spring Boot", "Express", "Gin", "Rails", "Laravel", "ASP.NET"]),
                "repository": f"https://github.com/{fake.user_name()}/{fake.word()}",
                "deployment_method": random.choice(["Docker", "Kubernetes", "VM", "Serverless"]),
                "environment": random.choice(["Production", "Staging", "Development"]),
                "owner_team": fake.job(),
                "health_status": random.choice(["Healthy", "Degraded", "Down"]),
                "dependencies": random.sample(["redis", "postgres", "mongodb", "rabbitmq", "elasticsearch"], k=random.randint(1, 3)),
                "last_deployed": fake.date_time_between(start_date="-30d").isoformat()
            })
        return apps


# ============================================================================
# THREAT INTELLIGENCE DATA
# ============================================================================

class FakeThreatData(DataTemplate):
    """Generate fake cybersecurity threat data"""

    THREAT_TYPES = [
        "Malware", "Phishing", "Ransomware", "DDoS", "SQL Injection",
        "XSS", "Zero-Day", "APT", "Brute Force", "Man-in-the-Middle"
    ]

    MALWARE_FAMILIES = [
        "Emotet", "TrickBot", "Ryuk", "Dridex", "Zeus",
        "CobaltStrike", "Mimikatz", "MetaSploit", "Gh0st"
    ]

    def generate_threats(self, count: int = 100) -> List[Dict]:
        """Generate fake threat indicators"""
        threats = []
        for i in range(count):
            threats.append({
                "threat_id": f"THR-{i+1:06d}",
                "title": f"{random.choice(self.THREAT_TYPES)} Campaign Detected",
                "threat_type": random.choice(self.THREAT_TYPES),
                "severity": random.choice(["Critical", "High", "Medium", "Low"]),
                "confidence": random.randint(50, 100),
                "first_seen": fake.date_time_between(start_date="-30d").isoformat(),
                "last_seen": fake.date_time_between(start_date="-7d").isoformat(),
                "indicators": {
                    "ip_addresses": [fake.ipv4_public() for _ in range(random.randint(1, 5))],
                    "domains": [fake.domain_name() for _ in range(random.randint(1, 3))],
                    "file_hashes": [fake.sha256() for _ in range(random.randint(1, 3))],
                    "urls": [fake.url() for _ in range(random.randint(1, 4))]
                },
                "malware_family": random.choice(self.MALWARE_FAMILIES) if random.random() > 0.5 else None,
                "target_sectors": random.sample(["Financial", "Healthcare", "Government", "Retail", "Energy"], k=random.randint(1, 3)),
                "techniques": random.sample([
                    "T1566 - Phishing",
                    "T1486 - Data Encrypted for Impact",
                    "T1059 - Command and Scripting Interpreter",
                    "T1203 - Exploitation for Client Execution"
                ], k=random.randint(1, 3)),
                "description": fake.text(max_nb_chars=300),
                "mitigation": fake.text(max_nb_chars=200)
            })
        return threats


# ============================================================================
# IT SECURITY DATA
# ============================================================================

class FakeSecurityData(DataTemplate):
    """Generate fake IT security event data"""

    def generate_security_events(self, count: int = 200) -> List[Dict]:
        """Generate fake security events/logs"""
        events = []
        for i in range(count):
            events.append({
                "event_id": f"EVT-{i+1:08d}",
                "timestamp": fake.date_time_between(start_date="-7d").isoformat(),
                "event_type": random.choice([
                    "Failed Login", "Successful Login", "Privilege Escalation",
                    "Firewall Block", "IDS Alert", "File Access", "Configuration Change"
                ]),
                "severity": random.choice(["Info", "Warning", "High", "Critical"]),
                "source_ip": fake.ipv4(),
                "destination_ip": fake.ipv4(),
                "user": fake.user_name(),
                "hostname": f"{random.choice(['srv', 'ws', 'db'])}-{fake.word()}",
                "action_taken": random.choice(["Allowed", "Blocked", "Alerted", "Quarantined"]),
                "description": fake.text(max_nb_chars=150),
                "tags": random.sample(["authentication", "network", "malware", "policy", "anomaly"], k=random.randint(1, 2))
            })
        return events

    def generate_vulnerabilities(self, count: int = 50) -> List[Dict]:
        """Generate fake vulnerability scan results"""
        vulns = []
        for i in range(count):
            vulns.append({
                "vuln_id": f"VULN-{i+1:06d}",
                "cve_id": f"CVE-{random.randint(2020, 2026)}-{random.randint(1000, 99999)}",
                "title": fake.catch_phrase(),
                "severity": random.choice(["Critical", "High", "Medium", "Low"]),
                "cvss_score": round(random.uniform(0.1, 10.0), 1),
                "affected_assets": random.randint(1, 50),
                "asset_type": random.choice(["Server", "Workstation", "Network Device", "Application"]),
                "discovery_date": fake.date_between(start_date="-30d").isoformat(),
                "status": random.choice(["Open", "In Progress", "Remediated", "Accepted Risk"]),
                "remediation": fake.text(max_nb_chars=200),
                "patch_available": random.choice([True, False])
            })
        return vulns


# ============================================================================
# TECH SUPPORT DATA
# ============================================================================

class FakeTechSupportData(DataTemplate):
    """Generate fake tech support ticket data"""

    WINDOWS_ISSUES = [
        "Blue Screen of Death (BSOD)",
        "Windows Update Failure",
        "Slow Performance",
        "Application Crashes",
        "Network Connectivity Issues",
        "Printer Not Working",
        "Sound Not Working"
    ]

    LINUX_ISSUES = [
        "Permission Denied Errors",
        "Kernel Panic",
        "Package Dependency Issues",
        "Network Interface Down",
        "Disk Space Full",
        "Service Won't Start",
        "SSH Connection Refused"
    ]

    MAC_ISSUES = [
        "Application Frozen",
        "Wi-Fi Keeps Disconnecting",
        "Time Machine Backup Failed",
        "Bluetooth Not Working",
        "Screen Flickering",
        "iCloud Sync Issues",
        "Spotlight Not Working"
    ]

    def generate_tickets(self, os_type: str = "all", count: int = 100) -> List[Dict]:
        """Generate fake support tickets"""
        tickets = []

        for i in range(count):
            if os_type == "windows":
                issue = random.choice(self.WINDOWS_ISSUES)
                platform = "Windows 11"
            elif os_type == "linux":
                issue = random.choice(self.LINUX_ISSUES)
                platform = random.choice(["Ubuntu 22.04", "CentOS 8", "Fedora 37"])
            elif os_type == "macos":
                issue = random.choice(self.MAC_ISSUES)
                platform = random.choice(["macOS Ventura", "macOS Monterey"])
            else:
                all_issues = self.WINDOWS_ISSUES + self.LINUX_ISSUES + self.MAC_ISSUES
                issue = random.choice(all_issues)
                platform = random.choice(["Windows 11", "Ubuntu 22.04", "macOS Ventura"])

            created = fake.date_time_between(start_date="-30d")
            tickets.append({
                "ticket_id": f"TKT-{i+1:06d}",
                "user": {
                    "name": fake.name(),
                    "email": fake.email(),
                    "phone": fake.phone_number(),
                    "department": fake.job()
                },
                "issue": issue,
                "platform": platform,
                "priority": random.choice(["Low", "Medium", "High", "Critical"]),
                "status": random.choice(["New", "In Progress", "Waiting on User", "Resolved", "Closed"]),
                "created_at": created.isoformat(),
                "updated_at": (created + timedelta(hours=random.randint(1, 72))).isoformat(),
                "assigned_to": fake.name(),
                "category": random.choice(["Hardware", "Software", "Network", "Account", "Other"]),
                "description": fake.text(max_nb_chars=300),
                "resolution_notes": fake.text(max_nb_chars=200) if random.random() > 0.3 else None,
                "attachments": random.randint(0, 3)
            })

        return tickets


# ============================================================================
# DATA GENERATOR SERVICE
# ============================================================================

def generate_dataset(template: str, count: int = 100, **kwargs) -> Dict:
    """
    Generate fake data based on template

    Args:
        template: Template name (e.g., "medical_patients", "crime_incidents")
        count: Number of records to generate
        **kwargs: Additional template-specific parameters

    Returns:
        Dictionary with generated data
    """
    generators = {
        # Medical
        "medical_patients": lambda: FakeMedicalData().generate_patients(count),
        "medical_appointments": lambda: FakeMedicalData().generate_appointments(kwargs.get("patient_ids", []), count),
        "medical_prescriptions": lambda: FakeMedicalData().generate_prescriptions(kwargs.get("patient_ids", []), count),

        # Crime
        "crime_incidents": lambda: FakeCrimeData().generate_incidents(count),
        "crime_suspects": lambda: FakeCrimeData().generate_suspects(kwargs.get("incident_ids", []), count),

        # IT
        "it_servers": lambda: FakeITData().generate_servers(count),
        "it_applications": lambda: FakeITData().generate_applications(count),

        # Threats
        "threat_indicators": lambda: FakeThreatData().generate_threats(count),

        # Security
        "security_events": lambda: FakeSecurityData().generate_security_events(count),
        "security_vulnerabilities": lambda: FakeSecurityData().generate_vulnerabilities(count),

        # Tech Support
        "support_tickets": lambda: FakeTechSupportData().generate_tickets(kwargs.get("os_type", "all"), count),
    }

    if template not in generators:
        raise ValueError(f"Unknown template: {template}")

    data = generators[template]()

    return {
        "template": template,
        "count": len(data),
        "generated_at": datetime.utcnow().isoformat(),
        "data": data
    }

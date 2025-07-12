import os
import smtplib
import requests
import json
import time
import re
import logging
import csv
from bs4 import BeautifulSoup
from email.message import EmailMessage
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('job_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class JobBot:
    def __init__(self, config: Dict):
        self.email = config['email']
        self.app_password = config['app_password']
        self.cv_path = config['cv_path']
        self.run_interval_hours = config['run_interval_hours']
        self.job_keywords = config['job_keywords']
        self.applied_jobs_log = config['applied_jobs_log']
        self.rate_limit_delay = config.get('rate_limit_delay', 2)
        
        # Ensure log file exists
        Path(self.applied_jobs_log).touch()
    
    def send_email(self, subject: str, body: str, attachment: Optional[str] = None, to_email: Optional[str] = None) -> bool:
        """Send email with optional attachment"""
        try:
            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = self.email
            msg['To'] = to_email or self.email
            msg.set_content(body)

            if attachment and Path(attachment).exists():
                with open(attachment, "rb") as f:
                    file_data = f.read()
                    filename = Path(attachment).name
                    msg.add_attachment(file_data, maintype="application", subtype="pdf", filename=filename)

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(self.email, self.app_password)
                smtp.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email or self.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return False
    
    def generate_cover_letter(self, job_title: str, company: str = "") -> str:
        """Generate personalized cover letter"""
        company_line = f" at {company}" if company and company != "Unknown" else ""
        
        return f"""Dear Hiring Team,

I'm writing to express my strong interest in the {job_title} position{company_line}. With a diverse background spanning banking operations, credit analysis, and hands-on software development, I bring a unique combination of administrative expertise and technical skills.

My experience includes:
• Developing smart IoT systems and CRM applications
• Banking operations and credit analysis
• Full-stack web development
• Technical support and system administration

I'm particularly drawn to roles that combine operational excellence with innovation. I believe my blend of business acumen and technical capabilities would be valuable to your team.

I've attached my CV for your review and would welcome the opportunity to discuss how I can contribute to your organization's success.

Best regards,
Mukrim Mohamed
{self.email}
+94 75 5545 015"""

    def extract_email(self, text: str) -> Optional[str]:
        """Extract email address from text"""
        if not text:
            return None
        match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
        return match.group(0) if match else None

    def job_already_applied(self, url: str) -> bool:
        """Check if job was already applied to"""
        try:
            with open(self.applied_jobs_log, "r") as file:
                return url in file.read()
        except FileNotFoundError:
            return False

    def mark_as_applied(self, job_data: Dict):
        """Mark job as applied with timestamp"""
        try:
            with open(self.applied_jobs_log, "a", newline='') as file:
                writer = csv.writer(file)
                writer.writerow([
                    datetime.now().isoformat(),
                    job_data['url'],
                    job_data['title'],
                    job_data['company']
                ])
        except Exception as e:
            logger.error(f"Failed to log applied job: {str(e)}")

    def matches_keywords(self, text: str) -> bool:
        """Check if text matches any job keywords"""
        if not text:
            return False
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.job_keywords)

    def fetch_remoteok_jobs(self) -> List[Dict]:
        """Fetch jobs from RemoteOK"""
        try:
            url = "https://remoteok.io/api"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            jobs = response.json()
            job_list = []
            
            for job in jobs[1:]:  # Skip first element (metadata)
                title = job.get("position") or job.get("title", "")
                desc = job.get("description", "")
                
                if self.matches_keywords(title) or self.matches_keywords(desc):
                    link = job.get("url", "")
                    if link and not self.job_already_applied(link):
                        job_data = {
                            "title": title,
                            "company": job.get("company", "Unknown"),
                            "url": link,
                            "email": self.extract_email(desc),
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "source": "RemoteOK"
                        }
                        job_list.append(job_data)
                        self.mark_as_applied(job_data)
            
            logger.info(f"Found {len(job_list)} new jobs from RemoteOK")
            return job_list
            
        except Exception as e:
            logger.error(f"Error fetching RemoteOK jobs: {str(e)}")
            return []

    def fetch_wwr_jobs(self) -> List[Dict]:
        """Fetch jobs from WeWorkRemotely"""
        try:
            url = "https://weworkremotely.com"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'en-GB,en-US;q=0.9,en;q=0.8,si;q=0.7,ja;q=0.6,ta;q=0.5,zh;q=0.4',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            # Add session for better request handling
            session = requests.Session()
            session.headers.update(headers)
            
            response = session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            job_list = []

            for section in soup.find_all("section", class_="jobs"):
                for li in section.find_all("li", class_=False):
                    link_tag = li.find("a", href=True)
                    if link_tag:
                        link = "https://weworkremotely.com" + link_tag['href']
                        title_elem = li.find("span", class_="title")
                        company_elem = li.find("span", class_="company")
                        
                        if title_elem and self.matches_keywords(title_elem.text):
                            if not self.job_already_applied(link):
                                job_data = {
                                    "title": title_elem.text.strip(),
                                    "company": company_elem.text.strip() if company_elem else "Unknown",
                                    "url": link,
                                    "email": None,
                                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                    "source": "WeWorkRemotely"
                                }
                                job_list.append(job_data)
                                self.mark_as_applied(job_data)
            
            logger.info(f"Found {len(job_list)} new jobs from WeWorkRemotely")
            return job_list
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                logger.warning("WeWorkRemotely blocked our request (403). Skipping this source for now.")
            else:
                logger.error(f"HTTP Error fetching WeWorkRemotely jobs: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error fetching WeWorkRemotely jobs: {str(e)}")
            return []

    def fetch_remotive_jobs(self) -> List[Dict]:
        """Fetch jobs from Remotive"""
        try:
            url = "http://remotive.io/api/remote-jobs"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            job_list = []

            for job in data.get("jobs", []):
                title = job.get("title", "")
                desc = job.get("description", "")
                
                if self.matches_keywords(title) or self.matches_keywords(desc):
                    link = job.get("url", "")
                    if link and not self.job_already_applied(link):
                        job_data = {
                            "title": title,
                            "company": job.get("company_name", "Unknown"),
                            "url": link,
                            "email": self.extract_email(desc),
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "source": "Remotive"
                        }
                        job_list.append(job_data)
                        self.mark_as_applied(job_data)
            
            logger.info(f"Found {len(job_list)} new jobs from Remotive")
            return job_list
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 526:
                logger.warning("Remotive API is temporarily unavailable (526). Will retry next cycle.")
            else:
                logger.error(f"HTTP Error fetching Remotive jobs: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error fetching Remotive jobs: {str(e)}")
            return []

    def fetch_all_jobs(self) -> List[Dict]:
        """Fetch jobs from all sources"""
        all_jobs = []
        
        # Add rate limiting between sources
        sources = [
            ("RemoteOK", self.fetch_remoteok_jobs),
            ("WeWorkRemotely", self.fetch_wwr_jobs),
            ("Remotive", self.fetch_remotive_jobs)
        ]
        
        for source_name, source_func in sources:
            try:
                logger.info(f"Fetching jobs from {source_name}...")
                jobs = source_func()
                all_jobs.extend(jobs)
                logger.info(f"Successfully fetched {len(jobs)} jobs from {source_name}")
                time.sleep(self.rate_limit_delay)  # Rate limiting
            except Exception as e:
                logger.error(f"Error in source {source_name}: {str(e)}")
                continue
        
        # Remove duplicates based on URL
        unique_jobs = []
        seen_urls = set()
        for job in all_jobs:
            if job['url'] not in seen_urls:
                unique_jobs.append(job)
                seen_urls.add(job['url'])
        
        if len(all_jobs) != len(unique_jobs):
            logger.info(f"Removed {len(all_jobs) - len(unique_jobs)} duplicate jobs")
        
        return unique_jobs

    def apply_to_job(self, job: Dict) -> bool:
        """Apply to a single job"""
        try:
            subject = f"Application for {job['title']} - Mukrim Mohamed"
            cover_letter = self.generate_cover_letter(job['title'], job['company'])
            
            if job['email']:
                success = self.send_email(
                    subject=subject,
                    body=cover_letter,
                    attachment=self.cv_path,
                    to_email=job['email']
                )
                if success:
                    logger.info(f"Applied to {job['title']} at {job['company']} via {job['email']}")
                return success
            else:
                logger.info(f"No email found for {job['title']} at {job['company']}")
                return False
                
        except Exception as e:
            logger.error(f"Error applying to job {job['title']}: {str(e)}")
            return False

    def get_stats(self) -> Dict:
        """Get bot statistics"""
        try:
            if not Path(self.applied_jobs_log).exists():
                return {"total_applications": 0, "last_run": "Never"}
            
            with open(self.applied_jobs_log, 'r') as file:
                lines = file.readlines()
                total_applications = len(lines)
                
            return {
                "total_applications": total_applications,
                "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            return {"total_applications": 0, "last_run": "Error"}

    def run_job_search(self):
        """Main job search and application logic"""
        logger.info("Starting job search cycle...")
        
        # Get current stats
        stats = self.get_stats()
        logger.info(f"Current stats: {stats['total_applications']} total applications sent")
        
        jobs = self.fetch_all_jobs()
        
        if not jobs:
            logger.info("No new jobs found this cycle")
            self.send_email(
                "Job Bot Update - No New Jobs",
                f"No new matching jobs found in this cycle.\n\nTotal applications sent so far: {stats['total_applications']}\n\nWill try again in {self.run_interval_hours} hours."
            )
            return
        
        logger.info(f"Found {len(jobs)} new jobs to process")
        
        # Send summary email
        summary_body = f"Found {len(jobs)} new jobs:\n\n"
        applied_count = 0
        
        # Group jobs by source for better summary
        jobs_by_source = {}
        for job in jobs:
            source = job['source']
            if source not in jobs_by_source:
                jobs_by_source[source] = []
            jobs_by_source[source].append(job)
        
        for source, source_jobs in jobs_by_source.items():
            summary_body += f"--- {source} ({len(source_jobs)} jobs) ---\n"
            for job in source_jobs:
                summary_body += f"• {job['title']} at {job['company']}\n"
                summary_body += f"  {job['url']}\n"
                if job['email']:
                    summary_body += f"  📧 {job['email']}\n"
                summary_body += "\n"
                
                # Apply if email is available
                if job['email']:
                    if self.apply_to_job(job):
                        applied_count += 1
                    time.sleep(1)  # Rate limiting
            summary_body += "\n"
        
        new_total = stats['total_applications'] + applied_count
        summary_body += f"Applications sent this cycle: {applied_count}/{len(jobs)}\n"
        summary_body += f"Total applications sent: {new_total}\n"
        summary_body += f"Next check in {self.run_interval_hours} hours"
        
        self.send_email(
            f"🎯 Job Bot Update - {len(jobs)} New Jobs Found",
            summary_body,
            attachment=self.cv_path
        )
        
        logger.info(f"Job search cycle completed. Applied to {applied_count} jobs. Total: {new_total}")

    def run_continuous(self):
        """Run the bot continuously"""
        logger.info(f"Starting continuous job bot (checking every {self.run_interval_hours} hours)")
        
        while True:
            try:
                self.run_job_search()
                sleep_seconds = self.run_interval_hours * 3600
                logger.info(f"Sleeping for {self.run_interval_hours} hours...")
                time.sleep(sleep_seconds)
                
            except KeyboardInterrupt:
                logger.info("Job bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                time.sleep(300)  # Wait 5 minutes before retrying


def main():
    """Main function to run the job bot"""
    
    # Configuration
    config = {
        'email': os.getenv("EMAIL"),
        'app_password': os.getenv("APP_PASSWORD"),  # Replace with your Gmail app password
        'cv_path': "Mukrim_CV.pdf",
        'run_interval_hours': 12,
        'job_keywords': [
            "software engineer", "frontend", "backend", "developer", "admin",
            "support", "CRM", "IT", "fullstack", "web developer", "technical support",
            "python", "javascript", "react", "node.js", "django", "flask"
        ],
        'applied_jobs_log': "applied_jobs.csv",
        'rate_limit_delay': 2
    }
    
    # Validate required files
    if not Path(config['cv_path']).exists():
        logger.error(f"CV file not found: {config['cv_path']}")
        return
    
    if config['app_password'] == "your_app_password_here":
        logger.error("Please set your Gmail app password in the config")
        return
    
    # Initialize and run bot
    bot = JobBot(config)
    bot.run_continuous()


if __name__ == "__main__":
    main()

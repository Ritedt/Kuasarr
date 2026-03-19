# -*- coding: utf-8 -*-
# Kuasarr
# Project by weedo078 (Fork von https://github.com/rix1337)

"""DBC API endpoints for Kuasarr"""

import json

from bottle import request, abort, response

from kuasarr.downloads import fail
from kuasarr.providers import shared_state
from kuasarr.providers.captcha import push_jobs
from kuasarr.providers.captcha import create_captcha_client
from kuasarr.providers.captcha.base_client import (
    CaptchaClientError,
    CaptchaInsufficientCredits,
)
from kuasarr.providers.captcha.dbc_client import (
    create_dbc_client,
    DBCError,
    DBCInsufficientCredits,
    DBC_AFFILIATE_LINK,
)
from kuasarr.providers.captcha.twocaptcha_client import TWOCAPTCHA_AFFILIATE_LINK
from kuasarr.providers.log import info, debug
from kuasarr.providers.notifications import send_discord_message
from kuasarr.providers.statistics import StatsHelper


def setup_dbc_routes(app):
    """Setup DBC API routes."""
    
    @app.get("/dbc/api/status/")
    def dbc_status():
        """Get captcha service status including balance and job statistics."""
        try:
            from kuasarr.storage.config import Config
            
            dbc_enabled = shared_state.values.get("dbc_enabled", False)
            
            # Get captcha service config
            captcha_config = Config('Captcha')
            service = (captcha_config.get('service') or 'dbc').lower().strip()
            
            # Count protected packages
            protected = shared_state.get_db("protected").retrieve_all_titles() or []
            protected_count = len(protected)
            
            # Job statistics
            jobs = push_jobs.list_jobs()
            job_stats = {
                "total": len(jobs),
                "pending": sum(1 for j in jobs.values() if j.get("status") == "pending"),
                "processing": sum(1 for j in jobs.values() if j.get("status") == "processing"),
                "failed": sum(1 for j in jobs.values() if j.get("status") == "failed"),
            }
            
            # Get balance if enabled
            balance_info = None
            affiliate_link = DBC_AFFILIATE_LINK if service == 'dbc' else TWOCAPTCHA_AFFILIATE_LINK
            
            if dbc_enabled:
                try:
                    client = create_captcha_client(shared_state)
                    if client:
                        account = client.get_account_info()
                        balance_info = {
                            "balance_cents": account.balance,
                            "balance_dollars": account.balance_dollars,
                            "service": service,
                        }
                except (DBCInsufficientCredits, CaptchaInsufficientCredits):
                    balance_info = {
                        "balance_cents": 0,
                        "balance_dollars": 0,
                        "error": "No credits",
                        "affiliate_link": affiliate_link,
                    }
                except (DBCError, CaptchaClientError) as e:
                    balance_info = {"error": str(e)}
            
            return {
                "captcha_enabled": dbc_enabled,
                "captcha_service": service,
                "captcha_configured": bool(client) if dbc_enabled else False,
                "protected_packages": protected_count,
                "jobs": job_stats,
                "balance": balance_info,
                "affiliate_link": affiliate_link,
            }
        except Exception as e:
            return {"error": str(e)}
    
    @app.get("/dbc/api/balance/")
    def dbc_balance():
        """Get current captcha service account balance."""
        try:
            client = create_captcha_client(shared_state)
            if not client:
                return abort(503, "Captcha service not configured")
            
            try:
                account = client.get_account_info()
                return {
                    "user_id": account.user_id,
                    "balance_cents": account.balance,
                    "balance_dollars": account.balance_dollars,
                    "rate": account.rate,
                    "is_banned": account.is_banned,
                }
            except (DBCInsufficientCredits, CaptchaInsufficientCredits):
                return {
                    "balance_cents": 0,
                    "balance_dollars": 0,
                    "error": "No credits left",
                }
        except (DBCError, CaptchaClientError) as e:
            return abort(500, str(e))
        except Exception as e:
            return abort(500, str(e))
    
    @app.get("/dbc/api/service_status/")
    def dbc_service_status():
        """Get DBC service status (accuracy, solve time, overload)."""
        try:
            client = create_dbc_client(shared_state)
            if not client:
                return abort(503, "DBC not configured")
            
            status = client.get_service_status()
            return {
                "accuracy": status.accuracy,
                "solved_in_seconds": status.solved_in,
                "is_overloaded": status.is_overloaded,
            }
        except DBCError as e:
            return abort(500, str(e))
        except Exception as e:
            return abort(500, str(e))
    
    @app.get("/dbc/api/packages/")
    def dbc_packages():
        """Get list of protected packages waiting for captcha solving."""
        try:
            protected = shared_state.get_db("protected").retrieve_all_titles() or []
            packages = []
            
            for package_id, raw_data in protected:
                try:
                    data = json.loads(raw_data)
                    packages.append({
                        "id": package_id,
                        "title": data.get("title", "Unknown"),
                        "links_count": len(data.get("links", [])),
                        "has_session": bool(data.get("session")),
                        "password": bool(data.get("password")),
                    })
                except json.JSONDecodeError:
                    continue
            
            return {"packages": packages, "count": len(packages)}
        except Exception as e:
            return {"error": str(e)}
    
    @app.get("/dbc/api/jobs/")
    def dbc_jobs():
        """Get list of active captcha solving jobs."""
        try:
            jobs = push_jobs.list_jobs()
            job_list = []
            
            for job_id, job in jobs.items():
                job_list.append({
                    "id": job_id,
                    "status": job.get("status"),
                    "attempt": job.get("attempt", 1),
                    "created_at": job.get("created_at"),
                    "updated_at": job.get("updated_at"),
                    "title": (job.get("payload") or {}).get("title", "Unknown"),
                })
            
            return {"jobs": job_list, "count": len(job_list)}
        except Exception as e:
            return {"error": str(e)}
    
    @app.delete("/dbc/api/job/<job_id>/")
    def dbc_cancel_job(job_id):
        """Cancel a specific captcha solving job."""
        try:
            job = push_jobs.get_job(job_id)
            if not job:
                return abort(404, "Job not found")
            
            push_jobs.remove_job(job_id)
            info(f"DBC Job {job_id} manuell abgebrochen")
            
            return {"status": "cancelled", "job_id": job_id}
        except Exception as e:
            return abort(500, str(e))
    
    @app.post("/dbc/api/retry/<package_id>/")
    def dbc_retry_package(package_id):
        """Retry captcha solving for a specific package."""
        try:
            # Check if package exists
            raw_data = shared_state.get_db("protected").retrieve(package_id)
            if not raw_data:
                return abort(404, "Package not found")
            
            # Remove any existing job to allow retry
            push_jobs.remove_job(package_id)
            
            info(f"DBC Paket {package_id} für Retry markiert")
            
            return {"status": "retry_scheduled", "package_id": package_id}
        except Exception as e:
            return abort(500, str(e))
    
    @app.delete("/dbc/api/package/<package_id>/")
    def dbc_fail_package(package_id):
        """Mark a package as failed and remove it."""
        try:
            raw_data = shared_state.get_db("protected").retrieve(package_id)
            if not raw_data:
                return abort(404, "Package not found")
            
            data = json.loads(raw_data)
            title = data.get("title", package_id)
            
            # Mark as failed
            failed = fail(title, package_id, shared_state, reason="Manually marked as failed via DBC API")
            if failed:
                shared_state.get_db("protected").delete(package_id)
                push_jobs.remove_job(package_id)
                send_discord_message(shared_state, title=title, case="failed")
                StatsHelper(shared_state).increment_failed_decryptions_automatic()
                info(f"DBC Paket {title} manuell als fehlgeschlagen markiert")
                
                return {"status": "failed", "package_id": package_id, "title": title}
            
            return abort(500, "Failed to mark package as failed")
        except Exception as e:
            return abort(500, str(e))
    
    @app.post("/dbc/api/test_credentials/")
    def dbc_test_credentials():
        """Test DBC credentials by fetching balance."""
        try:
            data = request.json or {}
            authtoken = data.get("authtoken") or shared_state.values.get("dbc_config", {}).get("authtoken", "")
            
            if not authtoken:
                return abort(400, "No API token provided")
            
            from kuasarr.providers.captcha.dbc_client import DeathByCaptchaClient
            
            client = DeathByCaptchaClient(
                authtoken=authtoken,
                timeout=30,
                max_retries=1,
            )
            
            try:
                account = client.get_account_info()
                return {
                    "success": True,
                    "service": "dbc",
                    "user_id": account.user_id,
                    "balance_cents": account.balance,
                    "balance_dollars": account.balance_dollars,
                    "is_banned": account.is_banned,
                }
            except DBCInsufficientCredits:
                return {
                    "success": True,
                    "service": "dbc",
                    "balance_cents": 0,
                    "balance_dollars": 0,
                    "warning": "No credits left",
                    "affiliate_link": DBC_AFFILIATE_LINK,
                }
        except DBCError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @app.post("/dbc/api/test_2captcha/")
    def test_2captcha_credentials():
        """Test 2Captcha API key by fetching balance."""
        try:
            data = request.json or {}
            
            api_key = data.get("api_key", "")
            
            if not api_key:
                return abort(400, "No API key provided")
            
            from kuasarr.providers.captcha.twocaptcha_client import TwoCaptchaClient
            
            client = TwoCaptchaClient(
                api_key=api_key,
                timeout=30,
                max_retries=1,
            )
            
            try:
                account = client.get_account_info()
                return {
                    "success": True,
                    "service": "2captcha",
                    "balance_cents": account.balance,
                    "balance_dollars": account.balance_dollars,
                }
            except CaptchaInsufficientCredits:
                return {
                    "success": True,
                    "service": "2captcha",
                    "balance_cents": 0,
                    "balance_dollars": 0,
                    "warning": "No credits left",
                    "affiliate_link": TWOCAPTCHA_AFFILIATE_LINK,
                }
        except CaptchaClientError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

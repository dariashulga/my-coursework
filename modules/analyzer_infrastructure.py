import socket
import ssl
from datetime import datetime, timezone
import tldextract

try:
    import whois
except ImportError:
    whois = None


def get_domain_whois(domain_name):
    """
    Получает информацию о регистрации домена (Whois): дата создания, регистратор.
    """
    if not whois:
        return {"error": "Библиотека python-whois не установлена"}

    try:
        # Извлекаем чистый домен второго уровня (например, belta.by)
        ext = tldextract.extract(domain_name)
        registered_domain = ext.registered_domain or domain_name

        w = whois.whois(registered_domain)
        creation_date = w.creation_date

        if isinstance(creation_date, list):
            creation_date = creation_date[0]

        age_days = None
        if creation_date and isinstance(creation_date, datetime):
            if creation_date.tzinfo is not None:
                creation_date = creation_date.astimezone(timezone.utc).replace(tzinfo=None)
            age_days = (datetime.now() - creation_date).days

        return {
            "registered_domain": registered_domain,
            "creation_date": creation_date.strftime('%d.%m.%Y') if creation_date else "Неизвестно",
            "age_days": age_days,
            "registrar": w.registrar if hasattr(w, 'registrar') else "Неизвестно",
            "org": w.org if hasattr(w, 'org') else "Неизвестно",
            "is_suspicious_age": (age_days is not None and age_days < 30)
        }
    except Exception as e:
        return {
            "registered_domain": domain_name,
            "creation_date": "Не удалось получить",
            "age_days": None,
            "registrar": "Ошибка Whois",
            "error": str(e),
            "is_suspicious_age": False
        }


def get_ssl_and_ip_info(domain_name):
    """
    Проверяет IP-адрес сервера и наличие/валидность SSL-сертификата (HTTPS).
    """
    ext = tldextract.extract(domain_name)
    hostname = ext.registered_domain or domain_name

    info = {
        "ip_address": "Не определен",
        "has_ssl": False,
        "ssl_issuer": "Отсутствует",
        "ssl_expires": "Неизвестно"
    }

    # 1. Определение IP-адреса
    try:
        ip = socket.gethostbyname(hostname)
        info["ip_address"] = ip
    except Exception:
        pass

    # 2. Проверка SSL-сертификата
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, 443), timeout=3) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                info["has_ssl"] = True

                # Извлекаем кем выдан
                issuer = dict(x[0] for x in cert.get('issuer', []))
                info["ssl_issuer"] = issuer.get('organizationName', issuer.get('commonName', 'Действителен'))

                # Дата окончания
                not_after = cert.get('notAfter')
                if not_after:
                    expire_dt = datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
                    info["ssl_expires"] = expire_dt.strftime('%d.%m.%Y')
    except Exception:
        info["has_ssl"] = False

    return info


def analyze_infrastructure(domain_name):
    """
    Комплексная функция OSINT-аудита сетевой инфраструктуры источника.
    """
    whois_info = get_domain_whois(domain_name)
    ssl_info = get_ssl_and_ip_info(domain_name)

    return {
        "domain": domain_name,
        "whois": whois_info,
        "ssl": ssl_info
    }
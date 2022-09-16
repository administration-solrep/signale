from email.utils import formataddr
from html import unescape
from typing import Dict, Iterable, Iterator, List, Tuple

from more_itertools import partition, unique_everseen
from pyramid.registry import Registry
from pyramid.renderers import render
from pyramid.request import Request
from pyramid_mailer import get_mailer
from pyramid_mailer.mailer import Mailer
from pyramid_mailer.message import Message as MailMessage

from zam_repondeur.models import Amendement, DBSession, Dossier, Lecture, User
from zam_repondeur.resources import LectureResource
from zam_repondeur.services.clean import clean_all_html


def sort_emails(text: str) -> Tuple[List[str], List[str]]:
    emails = extract_all_emails(text)
    bad_emails, clean_emails = clean_all_emails(emails)
    return bad_emails, clean_emails


def extract_all_emails(text: str) -> Iterator[str]:
    emails = (line.strip() for line in text.split("\n"))
    clean_emails = (clean_all_html(email) for email in emails if email != "")
    unique_emails: Iterator[str] = unique_everseen(clean_emails)
    return unique_emails


def clean_all_emails(emails: Iterable[str]) -> Tuple[List[str], List[str]]:
    normalized_emails = (User.normalize_email(email) for email in emails)
    bad_emails, clean_emails = partition(is_email_valid, normalized_emails)
    return list(bad_emails), list(clean_emails)


def is_email_valid(email: str) -> bool:
    return User.email_is_well_formed(email) and User.email_is_allowed(email)


def send_new_users_invitations(
    mailer: Mailer,
    sender_user: User,
    users: List[User],
    contact_mail_from: str,
    titre_dossier: str,
    url_dossier: str,
    registry: Registry,
) -> int:
    # TODO: async?
    reply_to = formataddr((sender_user.name, sender_user.email))
    subject = (
        get_badge(registry)
        + "Invitation à rejoindre \
un dossier législatif sur Signale"
    )
    body = f"""
Bonjour,

Vous venez d’être invité à rejoindre Signale
par {sender_user}
pour participer au dossier législatif suivant :
{titre_dossier}

Vous pouvez y accéder via l’adresse suivante :
{url_dossier}

Bonne journée !

Ce message est généré automatiquement. Merci de ne pas y répondre.
            """
    for user in users:
        message = MailMessage(
            subject=subject,
            sender=contact_mail_from,
            recipients=[user.email],
            body=body.strip(),
            extra_headers={"reply-to": reply_to},
        )
        mailer.send(message)
    return len(users)


def send_existing_users_invitations(
    mailer: Mailer,
    sender_user: User,
    users: List[User],
    contact_mail_from: str,
    titre_dossier: str,
    url_dossier: str,
    registry: Registry,
) -> int:
    # TODO: async?
    reply_to = formataddr((sender_user.name, sender_user.email))
    subject = (
        get_badge(registry)
        + "Invitation à participer \
à un dossier législatif sur Signale"
    )
    body = f"""
Bonjour,

Vous venez d’être invité
par {sender_user} à participer
au dossier législatif suivant sur Signale :
{titre_dossier}

Vous pouvez y accéder via l’adresse suivante :
{url_dossier}

Bonne journée !

Ce message est généré automatiquement. Merci de ne pas y répondre.
            """
    for user in users:
        message = MailMessage(
            subject=subject,
            sender=contact_mail_from,
            recipients=[user.email],
            body=body.strip(),
            extra_headers={"reply-to": reply_to},
        )
        mailer.send(message)
    return len(users)


def send_coordinator_invitations(
    mailer: Mailer,
    sender_user: User,
    users: List[User],
    contact_mail_from: str,
    titre_dossier: str,
    url_dossier: str,
    registry: Registry,
) -> int:
    # TODO: async?
    reply_to = formataddr((sender_user.name, sender_user.email))
    subject = (
        get_badge(registry)
        + "Invitation à participer \
à un dossier législatif sur Signale en tant que coordinateur"
    )
    body = f"""
Bonjour,

Vous venez d’être invité
par {sender_user} à participer
au dossier législatif suivant sur Signale en tant que coordinateur :
{titre_dossier}

Vous pouvez y accéder via l’adresse suivante :
{url_dossier}

Bonne journée !

Ce message est généré automatiquement. Merci de ne pas y répondre.
            """
    for user in users:
        message = MailMessage(
            subject=subject,
            sender=contact_mail_from,
            recipients=[user.email],
            body=body.strip(),
            extra_headers={"reply-to": reply_to},
        )
        mailer.send(message)
    return len(users)


def send_transfer_warnings(
    coordinateurs: List[User],
    collapsed_amendements: List[Amendement],
    lecture_resource: LectureResource,
    request: Request,
) -> None:
    # Mise en place de template et de mail html comme ci-dessous
    # https://docs.pylonsproject.org/projects/pyramid_mailer/en/latest/
    # On utilise pas premailer pour intégrer les css
    mailer = get_mailer(request)
    contact_mail_from = request.registry.settings["zam.contact_mail_from"]
    lecture = lecture_resource.model()
    dossier = lecture_resource.dossier_resource.model()

    context = {
        "lecture": f"{lecture}",
        "lecture_url": request.resource_url(lecture_resource["amendements"]),
        "dossier": f"{dossier.titre}",
        "dossier_url": request.resource_url(lecture_resource.dossier_resource),
        "user": request.user,
        "badge": f"{get_badge(request.registry)}",
    }

    for amendement in collapsed_amendements:
        context["amendement"] = amendement
        context["amendement_url"] = request.resource_url(
            lecture_resource["amendements"][amendement.num_str], "amendement_edit"
        )
        subject = render(
            "mails/warn_dossier_banc.subject.txt", context, request=request
        )

        html_body = render(
            "mails/warn_dossier_banc.body.html", context, request=request
        )
        text_body = render("mails/warn_dossier_banc.body.txt", context, request=request)

        message = MailMessage(
            subject=subject,
            sender=contact_mail_from,
            recipients=[user.email for user in coordinateurs],
            body=text_body.strip(),
            html=html_body,
        )
        mailer.send(message)


def send_dossier_deleted(
    dossier: Dossier,
    user: User,
    contact_mail_from: str,
    mailer: Mailer,
    registry: Registry,
) -> None:
    titre = unescape(dossier.titre)
    subject = f"{get_badge(registry)}Suppression du dossier {titre}"
    body = f"""
Bonjour,

La suppression du dossier {titre} que vous avez demandé a été réalisée avec succès.

Bonne journée !

Ce message est généré automatiquement. Merci de ne pas y répondre.
            """

    html_body = f"""
<p>Bonjour,</p>

<p>La suppression du dossier {titre} que vous avez demandé a été \
réalisée avec succès.</p>

<p>Bonne journée !</p>

<p>Ce message est généré automatiquement. Merci de ne pas y répondre.</p>
            """

    message = MailMessage(
        subject=subject,
        sender=contact_mail_from,
        recipients=[user.email],
        body=body.strip(),
        html=html_body.strip(),
    )
    mailer.send(message)


def send_nouvelles_lecture(
    dossier: Dossier,
    dossier_url: str,
    contact_mail_from: str,
    mailer: Mailer,
    registry: Registry,
) -> None:

    # Récupération des admins
    admins = (
        DBSession.query(User).filter(User.admin_at.isnot(None)).all()  # type: ignore
    )

    # Mise en place de template et de mail html comme ci-dessous
    # https://docs.pylonsproject.org/projects/pyramid_mailer/en/latest/
    # On utilise pas premailer pour intégrer les css

    context = {
        "dossier": f"{dossier.titre}",
        "dossier_url": dossier_url,
        "badge": f"{get_badge(registry)}",
    }

    titre = unescape(dossier.titre)
    subject = (
        f"{get_badge(registry)}Signale - {titre} - Récupération de nouvelles lectures"
    )
    html_body = render("mails/nouvelle_lecture.body.html", context)
    text_body = f"""
De nouvelles lectures ont été récupérées pour le dossier {titre}.

{dossier_url}

Bonne journée !

Ce message est généré automatiquement. Merci de ne pas y répondre.
"""

    if admins:
        message = MailMessage(
            subject=subject,
            sender=contact_mail_from,
            recipients=[user.email for user in admins],
            body=text_body.strip(),
            html=html_body,
        )
        mailer.send(message)


def send_alert(registry: Registry, context: Dict[str, str]) -> None:

    contact_mail_from = registry.settings["zam.contact_mail_from"]
    mailer = get_mailer(registry)

    subject = f"{get_badge(registry)}Erreur de mise à jour de données"

    titre = context.get("titre", "")
    url = context.get("url", "")
    message = context.get("message", "")

    text_body = f"""
Bonjour,

La mise à jour de {titre} n’a pas pu être réalisée.

La donnée suivante présente une anomalie:

{url}

Message d'erreur:

{message}

Bonne journée !

Ce message est généré automatiquement. Merci de ne pas y répondre.
            """
    html_body = render("mails/alert.body.html", context)

    # Récupération des admins
    admins = (
        DBSession.query(User).filter(User.admin_at.isnot(None)).all()  # type: ignore
    )

    if admins:
        message = MailMessage(
            subject=subject,
            sender=contact_mail_from,
            recipients=[user.email for user in admins],
            body=text_body.strip(),
            html=html_body,
        )
        mailer.send(message)


def send_export_dossier_notification(
    registry: Registry, dossier_url: str, user: User, dossier: Dossier
) -> None:

    contact_mail_from = registry.settings["zam.contact_mail_from"]
    mailer = get_mailer(registry)
    duration = int(int(registry.settings["zam.users.export_dossier_duration"]) / 3600)

    context = {
        "user": user,
        "dossier_url": dossier_url,
        "dossier": dossier,
        "expire_at": duration,
    }

    titre = unescape(dossier.titre)
    subject = f"{get_badge(registry)}Export du dossier {titre}"
    html_body = render("mails/export_dossier_notification.body.html", context)
    text_body = f"""
Bonjour,

L’export complet du dossier {titre} que vous avez demandé est disponible sur Signale :

{dossier_url}/import_export

L’extraction sera disponible pendant {duration}h.

Bonne journée !

Ce message est généré automatiquement. Merci de ne pas y répondre.
            """

    message = MailMessage(
        subject=subject,
        sender=contact_mail_from,
        recipients=[user.email],
        body=text_body.strip(),
        html=html_body,
    )
    mailer.send(message)


def send_import_dossier_notification(
    registry: Registry, dossier_url: str, user: User, dossier: Dossier
) -> None:

    contact_mail_from = registry.settings["zam.contact_mail_from"]
    mailer = get_mailer(registry)

    context = {
        "user": user,
        "dossier_url": dossier_url,
        "dossier": dossier,
    }

    titre = unescape(dossier.titre)
    subject = f"{get_badge(registry)}Import du dossier {titre}"
    html_body = render("mails/import_dossier_notification.body.html", context)
    text_body = f"""
Bonjour,

L’import complet du dossier {titre} que vous avez demandé a été réalisé avec succès :

{dossier_url}

Bonne journée !

Ce message est généré automatiquement. Merci de ne pas y répondre.
            """

    message = MailMessage(
        subject=subject,
        sender=contact_mail_from,
        recipients=[user.email],
        body=text_body.strip(),
        html=html_body,
    )
    mailer.send(message)


def send_export_pdf_notification(
    registry: Registry, lecture_url: str, user: User, lecture: Lecture
) -> None:

    contact_mail_from = registry.settings["zam.contact_mail_from"]
    mailer = get_mailer(registry)
    duration = int(int(registry.settings["zam.users.export_pdf_duration"]) / 3600)

    context = {
        "user": user,
        "lecture_url": lecture_url,
        "lecture": f"{lecture}",
        "expire_at": duration,
    }

    titre = unescape(f"{lecture}")
    subject = f"{get_badge(registry)}Export PDF de la lecture {titre}"
    html_body = render("mails/export_pdf_notification.body.html", context)
    text_body = f"""
Bonjour,

L’export pdf de la lecture {titre} que vous avez demandé est disponible sur Signale :

{lecture_url}/import_export

Le pdf sera disponible pendant {duration}h.

Bonne journée !

Ce message est généré automatiquement. Merci de ne pas y répondre.
            """

    message = MailMessage(
        subject=subject,
        sender=contact_mail_from,
        recipients=[user.email],
        body=text_body.strip(),
        html=html_body,
    )
    mailer.send(message)


def send_manage_admins(is_grant: bool, request: Request, user: User) -> None:
    contact_mail_from: str = request.registry.settings["zam.contact_mail_from"]
    mailer: Mailer = get_mailer(request)

    # Récupération des admins
    admins = (
        DBSession.query(User)
        .filter(User.admin_at.isnot(None), User.pk != user.pk,)  # type: ignore
        .all()
    )

    # Mise en place de template et de mail html comme ci-dessous
    # https://docs.pylonsproject.org/projects/pyramid_mailer/en/latest/
    # On utilise pas premailer pour intégrer les css

    context = {
        "is_grant": is_grant,
        "user": user,
        "admin": request.user,
        "badge": f"{get_badge(request.registry)}",
    }

    subject = render("mails/manage_admins.subject.txt", context)
    html_body = render("mails/manage_admins.body.html", context)
    text_body = render("mails/manage_admins.body.txt", context)

    if admins:
        message = MailMessage(
            subject=subject,
            sender=contact_mail_from,
            recipients=[user.email for user in admins],
            body=text_body.strip(),
            html=html_body,
        )
        mailer.send(message)


def send_update_cache_completed(registry: Registry, user: User) -> None:
    contact_mail_from = registry.settings["zam.contact_mail_from"]
    mailer = get_mailer(registry)

    subject = f"{get_badge(registry)}Mise à jour du cache terminée"
    body = f"""
Bonjour,

La mise à jour du cache de l’application Signale que vous avez demandé est \
maintenant terminée.

Bonne journée !

Ce message est généré automatiquement. Merci de ne pas y répondre.
                """
    message = MailMessage(
        subject=subject,
        sender=contact_mail_from,
        recipients=[user.email],
        body=body.strip(),
    )
    mailer.send(message)


def get_badge(registry: Registry) -> str:
    badge = registry.settings.get("zam.menu_badge_label", "")
    return f"[{badge.upper()}] : " if badge else ""


def send_dossier_archived(
    dossier: Dossier,
    dossier_url: str,
    contact_mail_from: str,
    mailer: Mailer,
    registry: Registry,
) -> None:

    # Récupération des admins
    admins = (
        DBSession.query(User).filter(User.admin_at.isnot(None)).all()  # type: ignore
    )

    titre = unescape(dossier.titre)
    subject = f"{get_badge(registry)}Signale - {titre} - Archivage automatique"
    body = f"""Bonjour,

Suite à la promulgation de la loi {dossier.titre_loi}, le dossier législatif {titre}\
 associé a été archivé.

{dossier_url}

Bonne journée !

Ce message est généré automatiquement. Merci de ne pas y répondre.
"""

    if admins:
        message = MailMessage(
            subject=subject,
            sender=contact_mail_from,
            recipients=[user.email for user in admins],
            body=body.strip(),
        )
        mailer.send(message)

class Transfers extends Stimulus.Controller {
    static get targets() {
        return [
            'submitTo',
            'submitIndex',
            'submitDossierBanc',
            'amendementsWithTableActive',
            'amendementsWithTableInactive',
            'amendementsFromDossierDeBanc'
        ]
    }

    initialize() {
        this.verify()
    }

    check(event) {
        this.verify()
    }

    confirmTransfer(event) {
        const fromDossierDeBanc = this.hasCheckedElements(
            this.hasAmendementsFromDossierDeBancTarget
                ? this.amendementsFromDossierDeBancTarget
                : null
        )
        if (fromDossierDeBanc) {
            var result = confirm( "Attention ! La fiche de banc relative à un ou plusieurs amendements est validée. Confirmez-vous le transfert de cet amendement hors de la corbeille « Dossier de banc » ?" )
            if (!result){
                event.preventDefault()
            }
        }
    }

    verify() {
        const fromDossierDeBanc = this.hasCheckedElements(
            this.hasAmendementsFromDossierDeBancTarget
                ? this.amendementsFromDossierDeBancTarget
                : null
        )
        const hasActiveCheckedElements = this.hasCheckedElements(
            this.hasAmendementsWithTableActiveTarget
                ? this.amendementsWithTableActiveTarget
                : null
        )
        const hasInactiveCheckedElements = this.hasCheckedElements(
            this.hasAmendementsWithTableInactiveTarget
                ? this.amendementsWithTableInactiveTarget
                : null
        )
        if (fromDossierDeBanc) {
            this.dangerClasses()
            if (hasActiveCheckedElements){
                this.dangerDossierDeBanc()
            } else if (hasInactiveCheckedElements) {
                this.warningDossierDeBanc()
            } else {
                this.primaryDossierDeBanc()
            }
            return
        } 
        if (hasActiveCheckedElements)  {
            this.dangerClasses()
            this.dangerDossierDeBanc()
            return
        }
        if (hasInactiveCheckedElements) {
            this.warningClasses()
        } else {
            this.primaryClasses()
        }
    }

    hasCheckedElements(target) {
        if (!target) return false
        const checkboxes = Array.from(
            target.querySelectorAll('input[type="checkbox"]')
        )
        return checkboxes.some(amendement => amendement.checked)
    }

    // Sadly, Safari does not support classList.replace()
    dangerClasses() {
        this.submitToTarget.classList.add('danger')
        this.submitToTarget.classList.remove('primary')
        this.submitToTarget.classList.remove('warning')
        this.submitIndexTarget.classList.add('danger')
        this.submitIndexTarget.classList.remove('primary')
        this.submitIndexTarget.classList.remove('warning')
    }

    dangerDossierDeBanc() {
        this.submitDossierBancTarget.classList.add('danger')
        this.submitDossierBancTarget.classList.remove('primary')
        this.submitDossierBancTarget.classList.remove('warning')
    }

    warningClasses() {
        this.submitToTarget.classList.add('warning')
        this.submitToTarget.classList.remove('primary')
        this.submitToTarget.classList.remove('primary')
        this.submitIndexTarget.classList.add('warning')
        this.submitIndexTarget.classList.remove('primary')
        this.submitIndexTarget.classList.remove('primary')
        this.submitDossierBancTarget.classList.add('warning')
        this.submitDossierBancTarget.classList.remove('primary')
        this.submitDossierBancTarget.classList.remove('primary')
    }

    warningDossierDeBanc() {
        this.submitDossierBancTarget.classList.add('warning')
        this.submitDossierBancTarget.classList.remove('primary')
        this.submitDossierBancTarget.classList.remove('primary')
    }

    primaryClasses() {
        this.submitToTarget.classList.remove('warning')
        this.submitToTarget.classList.remove('danger')
        this.submitToTarget.classList.add('primary')
        this.submitIndexTarget.classList.remove('warning')
        this.submitIndexTarget.classList.remove('danger')
        this.submitIndexTarget.classList.add('primary')
        this.submitDossierBancTarget.classList.remove('warning')
        this.submitDossierBancTarget.classList.remove('danger')
        this.submitDossierBancTarget.classList.add('primary')
    }

    primaryDossierDeBanc() {
        this.submitDossierBancTarget.classList.remove('warning')
        this.submitDossierBancTarget.classList.remove('danger')
        this.submitDossierBancTarget.classList.add('primary')
    }
}

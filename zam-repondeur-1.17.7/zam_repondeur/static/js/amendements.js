application.register(
  'amendements-backlinks',
  class extends Stimulus.Controller {
    update(event) {
      event.preventDefault()
      const thisURL = new URL(window.location.href)
      const linkURL = new URL(event.target.href)
      thisURL.hash = ''
      linkURL.searchParams.set('back', thisURL.pathname + thisURL.search)
      const href = linkURL.toString()
      if (
        event.ctrlKey ||
        event.shiftKey ||
        event.metaKey || // apple
        (event.button && event.button == 1) // middle click, >IE9 + everyone else
      ) {
        window.open(href).focus()
      } else {
        window.location.replace(href)
      }
    }
  }
)

application.register(
  'amendements-selection',
  class extends Stimulus.Controller {
    static get targets() {
      return ['filters', 'checkAll']
    }
    initialize() {
      this.groupActions = this.element.querySelector('.groupActions')
      this.filters = this.element.querySelector('.filters')
      this.batchAmendementsLink = this.groupActions.querySelector(
        '#batch-amendements'
      )
      this.copyReponseLink = this.groupActions.querySelector(
        '#copy-amendements'
      )
      this.selectAllCheckbox = this.element.querySelector(
        'input[type="checkbox"][name="select-all"]'
      )
      // Useful in case of (soft) refresh with already checked box.
      this.selectAllCheckbox.checked = false
      this.checkboxes = this.element.querySelectorAll(
        'tbody input[type="checkbox"]:not([name="select-all"])'
      )
      const checkeds = this.element.querySelectorAll(
        'tbody input[type="checkbox"]:not([name="select-all"]):checked'
      )
      this.setStatus(this.selectAllCheckbox, this.checkboxes.length, checkeds.length)

      // Useful in case of (soft) refresh with already checked boxes.
      this.toggleGroupActions()
      this.checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', e => {
          this.toggleGroupActions()
        })
      })
    }

    fromSameArticle(checkeds) {
      const articleNumFromChecked = item =>
        item.closest('tr').dataset.article.trim()
      const firstArticleChecked = articleNumFromChecked(checkeds[0])
      return checkeds.every(
        checked => articleNumFromChecked(checked) === firstArticleChecked
      )
    }

    fromSameMission(checkeds) {
      const missionFromChecked = item =>
        item.closest('tr').dataset.mission
      const firstMissionChecked = missionFromChecked(checkeds[0])
      return checkeds.every(
        checked => missionFromChecked(checked) === firstMissionChecked
      )
    }

    toggleGroupActions() {
      const checkeds = Array.from(this.checkboxes).filter(box => box.checked)
      const checkedsLength = checkeds.length
      const filtersNotDisplayed = this.filters.classList.contains('d-none')
      this.groupActions.classList.toggle('d-none', checkedsLength < 1)
      if (this.batchAmendementsLink) {
        this.batchAmendementsLink.classList.toggle('d-none', checkedsLength < 2)
        if (checkedsLength >= 2) {
          this.batchAmendementsLink.classList.toggle(
            'd-none',
            !(this.fromSameArticle(checkeds) && this.fromSameMission(checkeds))
          )
        }
      }
      if (this.copyReponseLink) {
        this.copyReponseLink.classList.toggle('d-none', checkedsLength < 2)
      }

      if(checkedsLength == 0 && filtersNotDisplayed){
        this.groupActions.parentElement.classList.add('d-none')
      } else {
        this.groupActions.parentElement.classList.remove('d-none')
      }

      if (checkedsLength < 1) {
        this.filtersTarget
          .querySelectorAll('th')
          .forEach(th => (th.style.top = '0'))
      } else {
        this.filtersTarget
          .querySelectorAll('th')
          .forEach(th => (th.style.top = '3.8rem'))
      }
      if(this.groupActions.querySelector('#transfer_multiple_choices') != null){
        this.changeURLFormGivenChecks(
          this.groupActions.querySelector('#transfer_multiple_choices'),
          checkeds,
          checkedsLength
        )
      }
      if(this.groupActions.querySelector('#transfer_on_workspace') != null){
          this.changeURLFormGivenChecks(
            this.groupActions.querySelector('#transfer_on_workspace'),
            checkeds,
            checkedsLength
          )
      }
      this.changeURLGivenChecks(
        this.groupActions.querySelector('#export-pdf'),
        checkeds
      )
      if (checkedsLength >= 2 && this.batchAmendementsLink) {
        this.changeURLGivenChecks(this.batchAmendementsLink, checkeds)
      }
      if (checkedsLength >= 2 && this.copyReponseLink) {
        this.changeURLGivenChecks(this.copyReponseLink, checkeds)
      }
    }

    changeURLGivenChecks(target, checkeds) {
      const url = new URL(target.getAttribute('href'))
      url.searchParams.delete('nums')
      checkeds.forEach(checked => {
        url.searchParams.append('nums', checked.value)
      })
      target.setAttribute('href', url.toString())
    }
    changeURLFormGivenChecks(target, checkeds, checkedsLength) {
      const urlTransfer = new URL(target.dataset.urlTransfer)
      var nums = new Array()
      var countTransfer = 0
      var countOnMyTable = 0

      
      if(target.name == "transfer_multiple_choices"){
        // Delete input name 'nums'
        var numsToTransfer = document.getElementById('nums-to-transfer-multiple')
        numsToTransfer.innerHTML = ''

        target.setAttribute('action', urlTransfer.toString())
        target.children['submit-table'].disabled = false
      }

      if(target.name == "transfer_on_workspace"){
        // Delete input name 'nums'
        var numsToTransfer = document.getElementById('nums-to-transfer-workspace');
        numsToTransfer.innerHTML = '';
      }
      
      // For each amendement, set up urls and form infos
      checkeds.forEach(checked => {
        var readyToTransfer = checked.parentNode.parentNode.dataset.transfer
        var isOnMyTable = checked.parentNode.parentNode.dataset.onmytable
        countTransfer = countTransfer + parseInt(readyToTransfer)
        countOnMyTable = countOnMyTable + parseInt(isOnMyTable)
        nums.push(checked.value)
        var input = document.createElement("input");
        input.setAttribute("type", "hidden");
        input.setAttribute("name", "nums");
        input.setAttribute("value", checked.value);
        numsToTransfer.appendChild(input);
      })

      if(target.name == "transfer_on_workspace"){

        const urlWorkspace = new URL(target.dataset.urlWorkspace)
        if(countOnMyTable == checkedsLength){
          target.setAttribute('action', '#')
          target.children['submit-table'].classList.remove('warning')
          target.children['submit-table'].classList.add('disabled')
          target.children['submit-table'].disabled = true
        } else if(countTransfer < checkedsLength){
          target.children['submit-table'].classList.add('warning')
          target.children['submit-table'].classList.remove('disabled')
          target.children['submit-table'].disabled = false
          target.setAttribute('action', urlTransfer.toString())
        } else {
          target.setAttribute('action', urlWorkspace.toString())
          target.children['submit-table'].classList.remove('warning', 'disabled')
          target.children['submit-table'].disabled = false
        }
      }
    }

    selectAll(event) {
      const boxes = Array.from(this.checkboxes)
      const checkeds = boxes.filter(box => box.checked).length
      const boxesLength = boxes.length

      if(checkeds > 0 && checkeds !== boxesLength){
        // Etat indéterminé, on décoche
        event.target.checked = false;
      }

      this.checkboxes.forEach(checkbox => {
        if (checkbox.offsetParent !== null) {
          checkbox.checked = event.target.checked
        }
      })
      this.toggleGroupActions()
    }

    updateStatusCheckAll() {
      const boxes = Array.from(this.checkboxes)
      const checkeds = boxes.filter(box => box.checked).length
      this.setStatus(this.checkAllTarget, boxes.length, checkeds)
    }

    setStatus(target, boxesLength, checkedsLength){
      if (boxesLength == checkedsLength) {
        target.checked = true;
        target.indeterminate = false;
      } else if (checkedsLength == 0) {
        target.checked = false;
        target.indeterminate = false;
      } else {
        target.indeterminate = true;
        target.checked = false;
      }
    }
  }
)

application.register(
  'amendements-articles',
  class extends Stimulus.Controller {
    static get targets() {
      return ['list']
    }
    toggle(event) {
      this.listTarget.classList.toggle('d-none')
      this.element.scrollIntoView()
      event.preventDefault()
    }
  }
)

application.register(
  'amendement-help',
  class extends Stimulus.Controller {
    static get targets() {
      return ['content']
    }

    connect() {
      this.contentTarget.classList.add("v-hidden")
    }

    toggle(event) {
      this.contentTarget.classList.toggle("v-hidden")
      event.preventDefault()
    }
  }
)

class AmendementsFilters extends Stimulus.Controller {
  static get targets() {
    return [
      'row',
      'link',
      'actions',
      'count',
      'table',
      'tbody',
      'articleInput',
      'missionInput',
      'amendementInput',
      'gouvernementalCheckbox',
      'gouvernementalLabel',
      'objetLabel',
      'avisLabel',
      'reponseLabel',
      'tableInput',
      'emptytableCheckbox',
      'emptytableLabel',
      'modifiedLabel',
      'dossierDeBancLabel',
      'auteurInput'
    ]
  }

  initialize() {
    const articleFilter = this.getURLParam('article')
    if (articleFilter !== '') {
      this.toggle()
      this.articleInputTarget.value = articleFilter
      this.filterByArticle(articleFilter)
    }
    const missionFilter = this.getURLParam('mission')
    if (missionFilter !== '' && this.hasMissionInputTarget) {
      this.toggle()
      this.missionInputTarget.value = missionFilter
      this.filterByMission(missionFilter)
    }
    const auteurFilter = this.getURLParam('auteur')
    if (auteurFilter !== '' && this.hasAuteurInputTarget) {
      this.toggle()
      this.auteurInputTarget.value = auteurFilter
      this.filterByAuteur(auteurFilter)
    }
    const amendementFilter = this.getURLParam('amendement')
    if (amendementFilter !== '') {
      this.toggle()
      this.amendementInputTarget.value = amendementFilter
      this.filterByAmendement(amendementFilter)
    }
    const gouvernementalFilter = this.getURLParam('gouvernemental')
    if (gouvernementalFilter !== '') {
      this.toggle()
      this.gouvernementalCheckboxTarget.checked = true
      this.gouvernementalLabelTarget
        .querySelector('abbr')
        .classList.add('selected')
      this.filterByGouvernemental(gouvernementalFilter)
    }
    const objetFilter = this.getURLParam('objet')
    if (objetFilter !== '') {
      this.setLibelle(objetFilter, this.objetLabelTarget, 'objet', 'Avec', 'Sans', 'avec objet', 'sans objet', 'blue')
      this.filterByObjet(objetFilter)
    }
    const avisFilter = this.getURLParam('avis')
    if (avisFilter !== '') {
      this.setLibelle(avisFilter, this.avisLabelTarget, 'avis', 'Avec', 'Sans', 'avec avis', 'sans avis', 'blue')
      this.filterByAvis(avisFilter)
    }

    const reponseFilter = this.getURLParam('reponse')
    if (reponseFilter !== '') {
      this.setLibelle(reponseFilter, this.reponseLabelTarget, 'réponse', 'Avec', 'Sans', 'avec réponse', 'sans réponse', 'blue')
      this.filterByReponse(reponseFilter)
    }
    const tableFilter = this.getURLParam('table')
    if (tableFilter !== '') {
      this.toggle()
      this.tableInputTarget.value = tableFilter
      this.filterByTable(tableFilter)
    }
    const emptytableFilter = this.getURLParam('emptytable')
    if (emptytableFilter !== '') {
      this.toggle()
      this.emptytableCheckboxTarget.checked = true
      this.emptytableLabelTarget.querySelector('abbr').classList.add('selected')
      this.filterByEmptytable(emptytableFilter)
    }
    const modifiedFilter = this.getURLParam('modified')
    if(modifiedFilter !== ''){
      this.setLibelle(modifiedFilter, this.modifiedLabelTarget, 'modified', 'Avec', 'Sans', 'modifiés', 'non modifiés', 'blue')
      this.filterByModified(modifiedFilter)
    }
    const dossierDeBancFilter = this.getURLParam('dossierDeBanc')
    if (dossierDeBancFilter !== '') {
      this.setLibelle(dossierDeBancFilter, this.dossierDeBancLabelTarget, 'dossierbanc', 'Sortis', 'Vide', 'qui ont été transférés en-dehors de la corbeille « Dossier de banc »', 'qui ne sont jamais allés dans la corbeille « Dossier de banc »', 'danger')
      this.filterByDossierDeBanc(dossierDeBancFilter)
    }
    this.updateCount()
  }

  setLibelle(value, target, type, libwith, libwithout, titlewith, titlewithout, color){
    if(value == '0'){
        target.querySelector('abbr').className = ""
        target.querySelector('abbr').classList.add('status', 'blue', 'selected', 'fond50')
        target.querySelector('abbr').innerHTML = libwithout
        target.querySelector('abbr').setAttribute('title', 'Tous les amendements ' + titlewithout)
    } else if(value == '1'){
        target.querySelector('abbr').className = ""
        target.querySelector('abbr').innerHTML = libwith
        target.querySelector('abbr').classList.add('status', 'selected', color)
        target.querySelector('abbr').setAttribute('title', 'Tous les amendements ' + titlewith)
    } else if(value == '2'){
        if(type == "dossierbanc"){
            target.querySelector('abbr').className = ""
            target.querySelector('abbr').classList.add('status', 'selected', 'success')
            target.querySelector('abbr').innerHTML = "Banc"
            target.querySelector('abbr').setAttribute('title', 'Tous les amendements qui se situent dans la corbeille « Dossier de banc »')
        }
    } else {
        target.querySelector('abbr').className = ""
        target.querySelector('abbr').classList.add('status', 'blue')
        target.querySelector('abbr').innerHTML = "Tous"
        target.querySelector('abbr').setAttribute('title', 'Tous les amendements sans distinction')
    }
  }

  getURLParam(name) {
    const urlParams = new URLSearchParams(window.location.search)
    return urlParams.get(name) || ''
  }

  setURLParam(name, value) {
    if (history.replaceState) {
      const newURL = new URL(window.location.href)
      if (value !== '') {
        newURL.searchParams.set(name, value)
      } else {
        newURL.searchParams.delete(name)
      }
      window.history.replaceState({ path: newURL.href }, '', newURL.href)
    }
  }

  toggle(event) {
    if (this.hasLinkTarget && this.hasRowTarget) {
      this.linkTarget.classList.toggle('enabled')
      this.rowTarget.classList.toggle('d-none')

      const linkDisplayed = this.linkTarget.classList.contains('enabled')
      const actionsNotDisplayed = this.actionsTarget.classList.contains('d-none')
      if(!linkDisplayed && actionsNotDisplayed){
        this.rowTarget.parentElement.classList.add('d-none')
      } else {
        this.rowTarget.parentElement.classList.remove('d-none')
      }
    }
    if (event) event.preventDefault()
  }

  updateCount() {
    const initial = parseInt(this.data.get('initial-count'))
    const visibleRows = this.tbodyTarget.querySelectorAll(
      "tr[data-filtre='1']:not([class^=hidden]):not([class=limit-derouleur])"
    )
    const paginate = parseInt(this.data.get('paginate'))

    if (!paginate){
        if (!visibleRows.length) {
          this.countTarget.innerHTML = `Aucun amendement (${initial} au total)`
          this.filterLimitLine(visibleRows)
          return
        }
        const current = Array.from(visibleRows).reduce(
          (accumulator, currentValue) => {
            return accumulator + currentValue.dataset.amendement.split(',').length
          },
          0
        )
        const plural = current > 1 ? 's' : ''
        if (initial === current)
          this.countTarget.innerHTML = `${current} amendement${plural}`
        else
          this.countTarget.innerHTML = `${current} amendement${plural} (${initial} au total)`
    } else {
        if (!visibleRows.length) {
          this.countTarget.innerHTML = `0 amendement sur ${initial}`
          this.filterLimitLine(visibleRows)
          return
        }
        const current = Array.from(visibleRows).reduce(
          (accumulator, currentValue) => {
            return accumulator + currentValue.dataset.amendement.split(',').length
          },
          0
        )
        const plural = current > 1 ? 's' : ''
        if (initial === current)
          this.countTarget.innerHTML = `${current} amendement${plural}`
        else
          this.countTarget.innerHTML = `${current} amendement${plural} sur ${initial}`
    }

    this.filterLimitLine(visibleRows)
  }

  filterLimitLine(rows){
    var abandoned = false
    if(rows.length) rows.forEach(row => abandoned = row.dataset.isAbandoned == 1)
    const limit = this.tbodyTarget.querySelector("tr.limit-derouleur")
    if(limit) limit.classList.toggle("d-none", !abandoned)
  }

  filterArticle(event) {
    const value = event.target.value.trim()
    this.filterByArticle(value)
    this.setURLParam('article', value)
    this.updateCount()
  }

  filterMission(event) {
    const value = event.target.value.trim()
    this.filterByMission(value)
    this.setURLParam('mission', value)
    this.updateCount()
  }

  filterAuteur(event) {
    const value = event.target.value.trim()
    this.filterByAuteur(value)
    this.setURLParam('auteur', value)
    this.updateCount()
  }

  filterAmendement(event) {
    const value = event.target.value.trim()
    this.filterByAmendement(value)
    this.setURLParam('amendement', value)
    this.updateCount()
  }

  filterGouvernemental(event) {
    const checked = event.target.checked
    const value = checked ? '1' : ''
    this.gouvernementalLabelTarget
      .querySelector('abbr')
      .classList.toggle('selected', checked)
    this.filterByGouvernemental(value)
    this.setURLParam('gouvernemental', value)
    this.updateCount()
  }

  // Configuration bouton à 3 états
  getValue(type, target){
    if(this.getURLParam(type) == '1') {
        target.querySelector('abbr').classList.add('selected')
        return '0'
    } else if(this.getURLParam(type) == '0') {
        target.querySelector('abbr').classList.remove('selected')
        return ''
    } else {
        target.querySelector('abbr').classList.add('selected')
        return '1'
    }
  }

  filterObjet(event) {
    var value
    value = this.getValue('objet', this.objetLabelTarget)

    this.setLibelle(value, this.objetLabelTarget, 'objet', 'Avec', 'Sans', 'avec objet', 'sans objet', 'blue')
    this.filterByObjet(value)
    this.setURLParam('objet', value)
    this.updateCount()
  }

  filterAvis(event) {
    var value
    value = this.getValue('avis', this.avisLabelTarget)

    this.setLibelle(value, this.avisLabelTarget, 'avis', 'Avec', 'Sans', 'avec avis', 'sans avis', 'blue')
    this.filterByAvis(value)
    this.setURLParam('avis', value)
    this.updateCount()
  }

  filterReponse(event) {
    var value
    value = this.getValue('reponse', this.reponseLabelTarget)

    this.setLibelle(value, this.reponseLabelTarget, 'réponse', 'Avec', 'Sans', 'avec réponse', 'sans réponse', 'blue')
    this.setURLParam('reponse', value)
    this.filterByReponse(value)
    this.updateCount()
  }

  filterTable(event) {
    const value = event.target.value.trim()
    this.filterByTable(value)
    this.setURLParam('table', value)
    this.updateCount()
  }

  filterEmptytable(event) {
    const checked = event.target.checked
    const value = checked ? '1' : ''
    this.emptytableLabelTarget
      .querySelector('abbr')
      .classList.toggle('selected', checked)
    this.filterByEmptytable(value)
    this.setURLParam('emptytable', value)
    this.updateCount()
  }

  filterModified(event){
    var value
    value = this.getValue('modified', this.modifiedLabelTarget)

    this.setLibelle(value, this.modifiedLabelTarget, 'modified', 'Avec', 'Sans', 'modifiés', 'non modifiés', 'blue')
    this.setURLParam('modified', value)
    this.filterByModified(value)
    this.updateCount()
  }

  filterDossierDeBanc(event) {
    var value
    value = parseInt(this.getURLParam('dossierDeBanc'))
    if ( value === null ){
        value = -1
    }    
    if ( value  < 3 ){
        value = value + 1
    } else {
        value = 0
    }
    value = value.toString()

    this.setLibelle(value, this.dossierDeBancLabelTarget, 'dossierbanc', 'Sortis', 'Vide', 'qui ont été transférés en-dehors de la corbeille « Dossier de banc »', 'qui ne sont jamais allés dans la corbeille « Dossier de banc »', 'danger')
    this.filterByDossierDeBanc(value)
    this.setURLParam('dossierDeBanc', value)
    this.updateCount()
  }

  filterByArticle(value) {
    this.filterColumn('hidden-article', line => {
      if (!value) {
        return true
      }
      if (value.includes(' ')) {
        // Special case of `6 b` for `6 bis` for instance.
        return line.dataset.article.startsWith(value)
      } else {
        return line.dataset.article.trim() === value
      }
    })
  }

  filterByMission(value) {
    this.filterColumn('hidden-mission', line => {
      if (!value) {
        return true
      }
      return line.dataset.mission.startsWith(value.toLowerCase())
    })
  }

  filterByAuteur(value) {
    this.filterColumn('hidden-auteur', line => {
      if (!value) {
        return true
      }
      return line.dataset.auteur.toLowerCase().includes(value.toLowerCase())
    })
  }

  filterByAmendement(value) {
    this.filterColumn('hidden-amendement', line => {
      if (!value) {
        return true
      }
      return line.dataset.amendement.split(',').some(num => num === value)
    })
    this.tableTarget.classList.toggle('filtered-amendement', value)
  }

  filterByGouvernemental(value) {
    this.filterColumn('hidden-gouvernemental', line => {
      if (!value) {
        return true
      }
      return line.dataset.gouvernemental.trim() === value
    })
    this.tableTarget.classList.toggle('filtered-gouvernemental', value)
  }

  filterByObjet(value) {
    this.filterColumn('hidden-objet', line => {
        if(value == '0' || value == '1'){
            return line.dataset.objet.trim() === value
        } else {
            return true
        }
    })
    this.tableTarget.classList.toggle('filtered-objet', value)
  }

  filterByAvis(value) {
    this.filterColumn('hidden-avis', line => {
        if(value == '0' || value == '1'){
            return line.dataset.avis.trim() === value
        } else {
            return true
        }
    })
    this.tableTarget.classList.toggle('filtered-avis', value)
  }

  filterByReponse(value) {
    this.filterColumn('hidden-reponse', line => {
        if(value == '0' || value == '1'){
            return line.dataset.reponse.trim() === value
        } else {
            return true
        }
    })
    this.tableTarget.classList.toggle('filtered-reponse', value)
  }

  filterByTable(value) {
    this.filterColumn('hidden-table', line => {
      if (!value) {
        return true
      }
      return line.dataset.table.toLowerCase().includes(value.toLowerCase())
    })
    this.tableTarget.classList.toggle('filtered-table', value)
  }

  filterByEmptytable(value) {
    this.filterColumn('hidden-emptytable', line => {
      if (!value) {
        return true
      }
      return line.dataset.emptytable.trim() === value
    })
    this.tableTarget.classList.toggle('filtered-emptytable', value)
  }

  filterByModified(value){
    this.filterColumn('hidden-modified', line => {
        if(value == '0' || value == '1'){
            return line.dataset.modified.trim() === value
        } else {
            return true
        }
    })
    this.tableTarget.classList.toggle('filtered-modified', value)
  }

  filterByDossierDeBanc(value) {
    this.filterColumn('hidden-dossierDeBanc', line => {
        if(value == '0' || value == '1' || value == '2'){
            return line.dataset.dossierdebanc.trim() === value;
        } else {
            return true
        }
    })
    this.tableTarget.classList.toggle('filtered-dossierDeBanc', value)
  }

  filterColumn(className, shouldShow) {
    this.tbodyTarget.querySelectorAll("tr[data-filtre='1']").forEach(line => {
      line.classList.toggle(className, !shouldShow(line))
    })
  }
}

application.register(
  'multiple-clicks',
  class extends Stimulus.Controller {
    prevent(event) {
      const nameClass = event.target.id + '-icon'
      const initialValue = event.target.value
      event.target.classList.remove(nameClass)
      event.target.classList.add('disabled')
      event.target.value = 'En cours de traitement…'
      window.setTimeout(_ => {
        event.target.value = initialValue
        event.target.classList.add(nameClass)
        event.target.classList.remove('disabled')
      }, 1000 * 10) // Seconds.
    }
  }
)

application.register(
  'filename',
  class extends Stimulus.Controller {
    display(event) {
      const input = event.target
      const filename = input.files[0].name
      const label = this.element.querySelector('label[for="' + input.id + '"]')
      label.innerHTML = filename
    }
  }
)

application.register(
  'switch-pagination',
  class extends Stimulus.Controller {
    static targets = ["form", "hiddenInput"];

    doSwitch(event) {
        const input = event.target
        const value = input.checked ? '1' : '0'
        this.hiddenInputTarget.value = value
        this.formTarget.submit()
    }
  }
)

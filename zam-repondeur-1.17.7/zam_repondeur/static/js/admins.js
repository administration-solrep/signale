application.register(
  'admin',
  class extends Stimulus.Controller {
    remove(event) {
      if (
        window.confirm(
          'Êtes-vous sûr de vouloir retirer cette personne ? ' +
            '(elle ne sera plus administratrice mais conservera son accès à Signale)'
        )
      ) {
        return
      } else {
        event.preventDefault()
      }
    }
  }
)

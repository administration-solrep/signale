application.register(
  'switch-copy',
  class extends Stimulus.Controller {
    static get targets() {
      return [
        'avis',
        'objet',
        'reponse',
        'comments',
        'inputavis',
        'inputobjet',
        'inputreponse',
        'inputcomments'
      ]
    }

    doSwitch(event) {
      var target
      if(event.target.id == "switch-avis"){
        target = this.avisTarget
      } else if(event.target.id == "switch-objet"){
        target = this.objetTarget
      } else if(event.target.id == "switch-reponse"){
        target = this.reponseTarget
      } else {
        target = this.commentsTarget
      }
      target.classList.toggle('d-none')
    }

    unload(event){
      this.avisTarget.classList.remove('d-none')
      this.objetTarget.classList.remove('d-none')
      this.reponseTarget.classList.remove('d-none')
      this.commentsTarget.classList.remove('d-none')
      this.inputavisTarget.checked = true
      this.inputobjetTarget.checked = true
      this.inputreponseTarget.checked = true
      this.inputcommentsTarget.checked = true
    }
  }
)

document.addEventListener("DOMContentLoaded", () => {
    var $select_amendements = $(".select-amdt").selectize({
        plugins: ['no_results', 'selectize-plugin-a11y'],
        valueField: "num",
        labelField: "amendement",
        searchField: ["amendement"],
        openOnFocus: true,
        selectOnTab: true,
        closeAfterSelect: true,
        onInitialize: () => {
            $("#select-amdt-selectized").attr("spellcheck", "false")
            if($(".select-amdt").val() != 0){
                setFormDirty()
            }
        },
        onChange: (key) => {
            setFormDirty()
        },
        onLoad: () => {
            setGouv("False")
        }
    })

    $(".select-amdt").on("change", function(){
        const key = this.value
        if(key == 0){
            setInfos(this, '', '', '', '')
            setGouv("False")
        } else {
            setInfos(
                this,
                $("#" + key + "-avis").val(),
                $("#" + key + "-objet").val(),
                $("#" + key + "-reponse").val(),
                $("#" + key + "-comments").val(),
            )
            setGouv($("#" + key + "-gouv").val())
        }

        if(this.classList.contains("select-global") && $select_amendements.length > 1){
            $select_amendements[1].selectize.setValue(this.value)
            $select_amendements[2].selectize.setValue(this.value)
            $select_amendements[3].selectize.setValue(this.value)
            $select_amendements[4].selectize.setValue(this.value)
        }
    })
})

function setInfos(element, avis, objet, reponse, comments){
    if(element.classList.contains("select-global")){
        setAvis(avis)
        setObjet(objet)
        setReponse(reponse)
        setComments(comments)
    } else if(element.classList.contains("select-avis")){
        setAvis(avis)
    } else if(element.classList.contains("select-objet")){
        setObjet(objet)
    } else if(element.classList.contains("select-reponse")){
        setReponse(reponse)
    } else if(element.classList.contains("select-comments")){
        setComments(comments)
    }
}

function setAvis(avis){
    $("#avis option[value='" + avis + "']").prop('selected', true)
}

function setObjet(objet){
    tinymce.get('objet').setContent(objet)
}

function setReponse(reponse){
    tinymce.get('reponse').setContent(reponse)
}

function setComments(comments){
    decodedComments = $('<div>').html(DOMPurify.sanitize(comments)).text()
    $("#comments").val(decodedComments)
}

function setGouv(gouv){
    if(gouv == "True"){
        $("label[for='reponse']").html("Présentation de l’amendement")
    } else {
        $("label[for='reponse']").html("Réponse à l’amendement")
    }
}

function setFormDirty(){
    var controller = application.getControllerForElementAndIdentifier(
        document.getElementById('batch-amendements'),
        'unsaved-changes'
    )
    if(!controller){
        controller = application.getControllerForElementAndIdentifier(
            document.getElementById('copy-amendements'),
            'unsaved-changes'
        )
    }
    controller.setDirty()
}

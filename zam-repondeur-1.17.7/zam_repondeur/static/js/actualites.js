document.addEventListener("DOMContentLoaded", () => {
    const input_pj = $("#piece_jointe");
    const pj_changed = $("#pj_changed");
    const label_pj = $("#label_pj");
    const delete_pj = $("#delete-pj");
    const msg_actu = $("#message-actu");
    const div_actu = $(".edit-actualite");
    const div_news = $(".news");

    input_pj.on("change", function(e){
        var labelVal = label_pj.html();
        var fileName = ""
        if(this.files && this.files.length == 1){
            fileName = e.target.value.split("\\").pop()
        }
        if(fileName){
            label_pj.html(fileName)
            label_pj.attr("title", "Sélectionner un autre fichier")
            delete_pj.removeClass("d-none")
        } else {
            label_pj.html(labelVal)
        }
        pj_changed.val("1")
    })

    /* Delete PJ */
    delete_pj.on("click", function(){
        input_pj.val("")
        $(this).addClass("d-none")
        label_pj.html("Insérer une pièce jointe")
        label_pj.attr("title", "")
        pj_changed.val("1")
    })

    /* Hide message, Show form */
    $("#modify-actu").on("click", function(){
        hide_one_show_2nd(msg_actu, div_actu)
    })

    /* Hide form, show message */
    $("#cancel-actu").on("click", function(){
        hide_one_show_2nd(div_actu, msg_actu)
        $("#button-open-actu").removeClass("d-none")

        if(!msg_actu.html()){
            div_news.addClass("d-none")
        }
        location.reload();
        pj_changed.val("0")
    })

    /* Hide arrow button, show form */
    $("#button-open-actu").on("click", function(){
        hide_one_show_2nd(this, div_actu)
        div_news.removeClass("d-none")
    })
})

function hide_one_show_2nd(first, second){
    $(first).addClass("d-none")
    $(second).removeClass("d-none")
}

tinymce.init({
    selector: 'textarea.editable',
    language: 'fr_FR',
    menubar: false,
    plugins: 'lists fullscreen paste',
    toolbar:
        'undo redo | formatselect | bold italic removeformat | bullist numlist | alignleft aligncenter alignright alignjustify | cut copy paste | fullscreen',
    branding: false,
    elementpath: false,
    content_style: 'p, li { line-height: 1.5; margin: 1em 0; } ol { padding-left: 1rem; }',
    block_formats: 'Paragraphe=p',
    browser_spellcheck: true
})
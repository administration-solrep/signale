/* Bouton haut de page */
$(window).scroll(function () {
    if ($(this).scrollTop() < 50 ) {
        $( '#scrollUp' ).fadeOut();
    } else {
        $( '#scrollUp' ).fadeIn();
    }
});

// Pour afficher si utilisateur rafraîchi en bas de page
if ($(this).scrollTop() > 50 ) {
    $( '#scrollUp' ).show();
}
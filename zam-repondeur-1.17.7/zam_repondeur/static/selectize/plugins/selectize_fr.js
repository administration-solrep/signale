/*
    Selectize plugin "remove_button" display title in english.
    This is a temporary patch to change language.
    Créé par Sword le 08/06/2021
*/

Selectize.define( 'lang_fr', function( options ) {
    this.require('remove_button');
    var self = this;
    const TITLE = "Retirer l'élément"

    self.setup = (function () {
        var original = self.setup;
        return function () {
          original.apply(self, arguments);
          setTitle()
        };
    })();

    self.onChange = (function () {
        var original = self.onChange;
        return function () {
          original.apply(self, arguments);
          setTitle()
        };
    })();

    function setTitle(){
        if(typeof self.$control !== 'undefined'){
            children = self.$control[0].childNodes
            children.forEach(function(element){
                if(typeof element.childNodes[1] !== 'undefined'){
                    if(element.childNodes[1].classList.contains("remove")){
                        element.childNodes[1].setAttribute("title", TITLE)
                    }
                }
            });
        }
    }
});
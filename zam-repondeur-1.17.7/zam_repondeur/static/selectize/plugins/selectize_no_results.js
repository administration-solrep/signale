/*
    https://github.com/brianreavis/selectize.js/issues/470
    Selectize doesn't display anything to let the user know there are no results.
    This is a temporary patch to display a no results option when there are no
    options to select for the user.
    Source : https://gist.github.com/dwickwire/3b5c9485467b0d01ef24f7fdfa140d92
    Modifié par Sword le 16/02/2021
*/

Selectize.define( 'no_results', function( options ) {
    var self = this;

    options = $.extend({
        message: 'Aucun résultat trouvé.',

        html: function(data) {
            return (
                '<div class="selectize-dropdown ' + data.classNames + ' dropdown-empty-message">' +
                    '<div class="selectize-dropdown-content">' +
                        '<div class="option active">' + data.message + '</div>' +
                    '</div>' +
                '</div>'
            );
        }
    }, options );

    self.displayEmptyResultsMessage = function () {
        this.$empty_results_container.css( 'top', this.$control.outerHeight() );
        this.$empty_results_container.show();
    };

    self.refreshOptions = (function () {
        var original = self.refreshOptions;

        return function () {
            original.apply( self, arguments );
            this.hasOptions ? this.$empty_results_container.hide() :
                this.displayEmptyResultsMessage();
        }
    })();

    self.onKeyDown = (function () {
        var original = self.onKeyDown;

        return function ( e ) {
            original.apply( self, arguments );
            if ( e.keyCode === 27 ) {
                this.$empty_results_container.hide();
            }
        }
    })();

    self.onBlur = (function () {
        var original = self.onBlur;

        return function () {
            original.apply( self, arguments );
            this.$empty_results_container.hide();
        };
    })();

    self.setup = (function() {
        var original = self.setup;
        return function() {
            original.apply(self, arguments);
            self.$empty_results_container = $( options.html( $.extend( {
                classNames: self.$input.attr( 'class' ) }, options ) ) );
            self.$empty_results_container.insertBefore( self.$dropdown );
            self.$empty_results_container.hide();
        };
    })();
});
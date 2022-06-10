api_version = '0.1';

// This dummy script is basically simulating whatever UI the instrument has
// being told to request the config. It calls the relevant function from the instrument adapter
// and fetches the config without the config manager needing to do anything.
// This in contrast to the callback mechanism implemented in the 'Apply Config' button.

class InstrumentAdapter extends AdapterEndpoint{

    constructor(api_version=DEF_API_VERSION){

        super("instrument", api_version);

        this.curious_card = document.getElementById("curious");
        this.specific_card = document.getElementById("specific");
        this.random_card = document.getElementById("random");

        this.config_test_button = document.getElementById("send-config-test");
        this.config_test_button.addEventListener("click", () => this.get_config());

        this.reset_button = document.getElementById("update-display");
        this.reset_button.addEventListener("click", () => this.update_param_display());
    }

    get_config(){
        this.put('', 'request_config')
        this.update_param_display();
    }

    update_param_display(){
        this.get('certain_params/curious_num').then(response => {
            this.curious_card.innerHTML = "Curious: " + response.curious_num
        });
        this.get('certain_params/specific_num').then(response => {
            this.specific_card.innerHTML = "Specific: " + response.specific_num
        });
        this.get('certain_params/random_num').then(response => {
            this.random_card.innerHTML = "Random: " + response.random_num
        });
    }
}

$( document ).ready(function() {
instrument_adapter = new InstrumentAdapter();
});

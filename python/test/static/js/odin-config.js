api_version = '0.1';

class ManagerAdapter extends AdapterEndpoint{

    constructor(api_version=DEF_API_VERSION){

        super("manager", api_version);

        // Getting access to elements that require modification
        // layer group row, detail card are the two with live updates
        this.layer_group_row = document.getElementById("layer-group-row");

        this.details_card = document.getElementById("details-card");
        this.details_card_header = document.getElementById("details-card-header");
        this.details_card_body = document.getElementById("details-card-body");

        this.confirm_button = document.getElementById("confirm-button");
        this.clear_button = document.getElementById("clear-button");

        // update param display for instrument tab
        this.curious_card = document.getElementById("curious");
        this.specific_card = document.getElementById("specific");
        this.random_card = document.getElementById("random");

        // debug buttons
        this.debug_button = document.getElementById("buttons-button");
        this.debug_remove_button = document.getElementById("less-buttons-button");
        this.debug_button.addEventListener("click", () => this.debug_add_many_buttons());
        this.debug_remove_button.addEventListener("click", () => this.debug_remove_many_buttons());

        // attach actions to static elements
        this.confirm_button.addEventListener("click", () => this.initiate_callback());
        this.clear_button.addEventListener("click", () => this.clear_button_press());

        this.get('all_names')
        // get all the items and then other important setup values from selection
        .then(response => {
            this.all_names = response.all_names;

            this.get('selection')
            .then(response => {
                this.layer_num = response.selection.layer_num;
                this.valid_options = response.selection.valid_options;
                this.param_selection_names = response.selection.param_selection_names;

                this.create_list_groups();  // initialise buttons
            });
        })
    }

    create_list_groups(){
        // this function creates the relevant numbers of columns, list groups,
        // and populates them from the all_options value
        this.layer_group_row.innerHTML = "";  // clear row

        // ensure default card value
        this.update_details_card('Selection details will go here', 'This is the details card');

        for (let i=0; i < this.layer_num; i++) {

            var string_i = i.toString();
            var layer_group_col = document.createElement("div");
            layer_group_col.className = "col p-0 h-100 text-center";  // h-100 = scroll
            layer_group_col.id = "layer-col-" + string_i;

            var layer_label = document.createElement("label");
            layer_label.className = "";
            layer_label.htmlFor = layer_group_col.id;
            layer_label.innerText = "Layer " + string_i;

            // This row is necessary for individual scrolling of layer list groups.
            var layer_group_subrow = document.createElement("div");
            layer_group_subrow.className = "row-fluid h-100 overflow-auto border";  // overflow-auto = scrolling
            layer_group_subrow.id = "layer-subrow-" + string_i;

            var ul = document.createElement("ul");
            ul.className = "list-group";
            ul.id = "list-group-layer-" + string_i;

            this.all_names[i].forEach(name => {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.className = "list-group-item list-group-item-action list-group-item-info";
                btn.textContent = name;
                btn.value = name;
                btn.id = name  // id is just the name for convenience' sake.
                btn.disabled = true;  // buttons initially disabled for refreshing purposes.

                btn.addEventListener("click", (event) => this.layer_group_button_press(event));
                ul.appendChild(btn);
            });

            layer_group_subrow.appendChild(layer_label);
            layer_group_subrow.appendChild(ul);
            layer_group_col.appendChild(layer_group_subrow);
            this.layer_group_row.appendChild(layer_group_col);
        }
        // now check to see which buttons to enable.
        this.update_list_groups();
    }

    update_list_groups() {
        // enable buttons that are found in valid_options
        for (let i=0; i < this.layer_num; i++) {
            var id = "list-group-layer-" + i.toString();
            var ul = document.getElementById(id);

            // valid_options[i] is the layer of the buttons being checked
            // ul.children[j] looks at each button, checking them against that layer's valid options
            for (let j=0; j < ul.children.length; j++) {
                let item = ul.children[j];

                if (Object.values(this.valid_options[i]).includes(item.id) === false){
                    if (this.param_selection_names.includes(item.id)) {
                        item.className += "list-group-item list-group-item-action list-group-item-info active";
                        item.disabled = true;
                    }
                    item.disabled = true;
                    // if not a valid option but is a param selection, highlight
                    // then disable it
                }
                else {
                    item.disabled = false;  // enable button if it's found for initialising purposes
                }
            }
        }

        // Card always needs updating when the lists are updated
        this.get('selection/current_config')
        .then(response => {
            var current_config = response.current_config

            // get the adapter-re-ordered param_selection_names
            this.get('selection/param_selection_names')
            .then(response => {
                this.param_selection_names = response.param_selection_names;

                var card_header_names = "";
                this.param_selection_names.forEach(item => {
                    card_header_names += item + ", ";
                })
                var card_header = "Merging: " + card_header_names.slice(0, -2);

                // update card with requested current config and new header
                this.update_details_card(
                    current_config, card_header
                );
            })
        })
    }

    debug_add_many_buttons() {
        for (let i=0; i < this.layer_num; i++) {

            let ul_id = "list-group-layer-" + i.toString();
            var ul = document.getElementById(ul_id);

            // temp for purpose of testing scrolls
            for (let j = 0; j < 10; j++){
                var button = document.createElement("buttton");
                button.type = "button";
                button.className = "list-group-item list-group-item-action list-group-item-dark";
                button.textContent = "refresh to remove";
                button.id = "dummy-button-" + j.toString();
                ul.appendChild(button);
            }
            // end temp
        }
    }
    debug_remove_many_buttons() {
        for (let i=0; i < this.layer_num; i++){
            let ul_id = "list-group-layer-" + i.toString();
            var ul = document.getElementById(ul_id);

            for (let j=0; j<10; j++){
                let button_id = "dummy-button-" + j.toString();
                var button = document.getElementById(button_id);
                ul.removeChild(button);
            }
        }
    }

    update_details_card(data, header){
        // update the details card with the latest information
        this.details_card_body.innerHTML = JSON.stringify(data, undefined, 2);
        this.details_card_header.innerHTML = header;
    }

    layer_group_button_press(event){
        // this function gets the current selection, adds the pressed button to it,
        // puts the new selection list back, then updates the layer lists with new valid options.
        var selected_button = event.target.value;

        this.get('selection/param_selection_names')
        .then(response => {
            this.param_selection_names = response.param_selection_names;

            this.param_selection_names.push(selected_button);
            this.put(this.param_selection_names, 'selection/param_selection_names');

            this.get('selection/valid_options')
            .then(response => {
                this.valid_options = response.valid_options;
                this.update_list_groups();
            });
        });
    }

    initiate_callback(){
        console.log("Initiating instrument config-request callbacks.");
        this.put('', 'get_config');
    }

    clear_button_press(){
        // clear the parameter selection, and re-initialise the list groups
        this.param_selection_names = []
        this.put(this.param_selection_names, 'selection/param_selection_names');

        this.get('selection/valid_options')
        .then(response => {
            // valid_options is equal to all_options now, but valid options needs re-collecting
            this.valid_options = response.valid_options;
            this.create_list_groups();
        });
    }
}

$( document ).ready(function() {
    manager_adapter = new ManagerAdapter();
});

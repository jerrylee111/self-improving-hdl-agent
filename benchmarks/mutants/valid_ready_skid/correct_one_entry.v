module top_module(
    input logic clk,
    input logic reset,
    input logic in_valid,
    input logic [7:0] in_data,
    output logic in_ready,
    output logic out_valid,
    output logic [7:0] out_data,
    input logic out_ready
);
    logic full;
    logic [7:0] data_q;

    assign in_ready = !full || out_ready;
    assign out_valid = full ? 1'b1 : in_valid;
    assign out_data = full ? data_q : in_data;

    always_ff @(posedge clk) begin
        if (reset) begin
            full <= 1'b0;
            data_q <= 8'h00;
        end else begin
            if (full && out_ready) begin
                full <= 1'b0;
            end
            if (in_valid && in_ready && !out_ready) begin
                full <= 1'b1;
                data_q <= in_data;
            end
        end
    end
endmodule
